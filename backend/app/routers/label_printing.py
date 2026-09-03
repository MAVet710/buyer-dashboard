from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.inventory_quality import CoaDocumentService, MAX_COA_BYTES
from modules.operational_moats.printing import LabelPrintingService
from ..auth import RequestContext, get_request_context
from ..database import get_engine
from ..services.label_studio import LabelInventoryService
from ..services.label_studio_fast import FastLabelInventoryService
from ..services.label_studio_integrity import normalize_testing_label_source
from ..services.sandbox_policy import sandbox_execution_policy

router = APIRouter(prefix="/label-printing", tags=["label-printing"])
ADMIN_ROLES = {"dev", "admin"}
COA_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}


class PrinterPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    transport: str = "browser"
    printer_key: str = Field(default="", max_length=255)
    dpi: int = Field(default=203, ge=100, le=1200)
    width_mm: float = Field(default=50, gt=0, le=500)
    height_mm: float = Field(default=25, gt=0, le=500)


class PrintJobPayload(BaseModel):
    printer_profile_id: str
    template_id: str
    label_review_id: str
    copies: int = Field(default=1, ge=1, le=500)
    override_reason: str = Field(default="", max_length=512)
    render_data: dict[str, Any] = Field(default_factory=dict)


class PrintCompletePayload(BaseModel):
    success: bool
    error: str = Field(default="", max_length=2000)


def _printer(row) -> dict[str, Any]:
    return {key: getattr(row, key) for key in ("id", "name", "transport", "printer_key", "dpi", "width_mm", "height_mm", "active", "created_by", "created_at", "updated_at")}


def _job(row, *, include_content: bool = False) -> dict[str, Any]:
    result = {key: getattr(row, key) for key in ("id", "printer_profile_id", "template_id", "label_review_id", "product_id", "package_id", "copies", "format", "status", "override_reason", "queued_by", "dispatched_by", "queued_at", "dispatched_at", "completed_at", "last_error")}
    result["render_data"] = json.loads(row.render_data_json or "{}")
    if include_content:
        result["rendered_content"] = row.rendered_content
    return result


def _require_coa_write(context: RequestContext) -> None:
    if context.role.casefold() not in COA_ROLES:
        raise HTTPException(403, "Your role can view COA-backed labels but cannot attach or confirm COA evidence.")


async def _coa_bytes(file: UploadFile) -> bytes:
    payload = await file.read(MAX_COA_BYTES + 1)
    if not payload:
        raise HTTPException(422, "The uploaded COA is empty.")
    if len(payload) > MAX_COA_BYTES:
        raise HTTPException(413, "The COA exceeds the 15 MB upload limit.")
    return payload


@router.get("/sandbox-context")
def label_sandbox_context(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Expose DEV-only layout/rehearsal capability without changing compliance state."""
    return sandbox_execution_policy(
        engine,
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        role=context.role,
    )


@router.get("/inventory-sources")
def list_inventory_label_sources(
    summary: bool = Query(default=False),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Return on-hand label sources; summary mode avoids COA/render fan-out."""
    if summary:
        return FastLabelInventoryService(engine).list_summaries(context.organization_id, context.facility_id)
    return [
        normalize_testing_label_source(source)
        for source in LabelInventoryService(engine).list_sources(context.organization_id, context.facility_id)
    ]


@router.get("/inventory-sources/{lot_id}")
def get_inventory_label_source(
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        return FastLabelInventoryService(engine).get_source(context.organization_id, context.facility_id, lot_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/inventory-sources/{lot_id}/coa", status_code=201)
async def upload_inventory_coa_fallback(
    lot_id: str,
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Fallback-only COA attachment for the exact selected METRC package/tag."""
    _require_coa_write(context)
    try:
        document = CoaDocumentService(engine).ingest_for_lot(
            context.organization_id,
            context.facility_id,
            lot_id,
            payload=await _coa_bytes(file),
            filename=file.filename or "coa.pdf",
            content_type=file.content_type or "application/pdf",
            actor=context.user_id,
        )
        source = FastLabelInventoryService(engine).get_source(context.organization_id, context.facility_id, lot_id)
        return {"coa_document": document, "source": source}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/inventory-sources/{lot_id}/coa/{document_id}/confirm")
def confirm_inventory_coa_fallback(
    lot_id: str,
    document_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Explicitly confirm a fallback PDF when no METRC tag was readable in it."""
    _require_coa_write(context)
    try:
        document = CoaDocumentService(engine).confirm_for_lot(
            context.organization_id,
            context.facility_id,
            lot_id,
            document_id,
            actor=context.user_id,
        )
        source = FastLabelInventoryService(engine).get_source(context.organization_id, context.facility_id, lot_id)
        return {"coa_document": document, "source": source}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/coas")
def list_coa_library(
    limit: int = Query(default=250, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    return CoaDocumentService(engine).list_documents(context.organization_id, context.facility_id, limit=limit)


@router.post("/coas", status_code=201)
async def upload_coa_library_document(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Primary COA library intake. A readable METRC source/package tag is required."""
    _require_coa_write(context)
    try:
        return CoaDocumentService(engine).ingest_library(
            context.organization_id,
            context.facility_id,
            payload=await _coa_bytes(file),
            filename=file.filename or "coa.pdf",
            content_type=file.content_type or "application/pdf",
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/coas/{document_id}/file")
def get_coa_file(
    document_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        payload, filename, content_type = CoaDocumentService(engine).document_bytes(context.organization_id, context.facility_id, document_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    safe = quote(filename or "coa.pdf")
    return Response(
        content=payload,
        media_type=content_type or "application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{safe}"},
    )


@router.get("/printers")
def list_printers(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return [_printer(row) for row in LabelPrintingService(engine).list_printers(context.organization_id, context.facility_id)]


@router.post("/printers", status_code=201)
def create_printer(payload: PrinterPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in ADMIN_ROLES:
        raise HTTPException(403, "Admin or DEV access is required to configure printer profiles.")
    try:
        return _printer(LabelPrintingService(engine).create_printer(organization_id=context.organization_id, facility_id=context.facility_id, name=payload.name, actor=context.user_id, transport=payload.transport, printer_key=payload.printer_key, dpi=payload.dpi, width_mm=payload.width_mm, height_mm=payload.height_mm))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/jobs")
def list_jobs(statuses: str = "", limit: int = Query(default=250, ge=1, le=1000), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    wanted = tuple(value.strip().casefold() for value in statuses.split(",") if value.strip())
    return [_job(row) for row in LabelPrintingService(engine).list_jobs(context.organization_id, context.facility_id, statuses=wanted, limit=limit)]


@router.post("/jobs", status_code=201)
def queue_print_job(payload: PrintJobPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = LabelPrintingService(engine).queue_job(organization_id=context.organization_id, facility_id=context.facility_id, printer_profile_id=payload.printer_profile_id, template_id=payload.template_id, label_review_id=payload.label_review_id, actor=context.user_id, role=context.role, render_data=payload.render_data, copies=payload.copies, override_reason=payload.override_reason)
        return _job(row, include_content=row.status == "rendered")
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_print_job(job_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    rows = LabelPrintingService(engine).list_jobs(context.organization_id, context.facility_id, limit=1000)
    row = next((item for item in rows if item.id == job_id), None)
    if not row:
        raise HTTPException(404, "Print job was not found.")
    return _job(row, include_content=True)


@router.post("/jobs/{job_id}/complete")
def complete_browser_job(job_id: str, payload: PrintCompletePayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = LabelPrintingService(engine).complete_job(context.organization_id, context.facility_id, job_id, context.user_id, success=payload.success, error=payload.error)
        return _job(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
