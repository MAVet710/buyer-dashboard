from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.operational_moats.printing import LabelPrintingService
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/label-printing", tags=["label-printing"])
ADMIN_ROLES = {"dev", "admin"}


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
