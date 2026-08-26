"""Service-account endpoints for DoobieLogic edge/ZPL printer agents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.operational_moats.external_api import authenticate_service_account
from modules.operational_moats.printing import LabelPrintingService
from .external_api import _facility, _token
from ..database import get_engine

router = APIRouter(prefix="/external/v1/print-jobs", tags=["external-printing"])


class PrintResult(BaseModel):
    success: bool
    error: str = Field(default="", max_length=2000)


def _ctx(engine: Engine, authorization: str, scope: str):
    try:
        return authenticate_service_account(engine, _token(authorization), scope)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc


def _job(row, include_content: bool = False):
    result = {
        "id": row.id,
        "printer_profile_id": row.printer_profile_id,
        "template_id": row.template_id,
        "label_review_id": row.label_review_id,
        "product_id": row.product_id,
        "package_id": row.package_id,
        "copies": row.copies,
        "format": row.format,
        "status": row.status,
        "queued_at": row.queued_at,
    }
    if include_content:
        result["rendered_content"] = row.rendered_content
    return result


@router.get("")
def pending_print_jobs(
    authorization: str = Header(default=""),
    x_facility_id: str = Header(default="", alias="X-Facility-Id"),
    limit: int = Query(default=50, ge=1, le=250),
    engine: Engine = Depends(get_engine),
):
    context = _ctx(engine, authorization, "printing:read")
    facility_id = _facility(engine, context, x_facility_id)
    rows = LabelPrintingService(engine).list_jobs(context.organization_id, facility_id, statuses=("queued",), limit=limit)
    return {"facility_id": facility_id, "jobs": [_job(row) for row in rows]}


@router.post("/{job_id}/claim")
def claim_print_job(
    job_id: str,
    authorization: str = Header(default=""),
    x_facility_id: str = Header(default="", alias="X-Facility-Id"),
    engine: Engine = Depends(get_engine),
):
    context = _ctx(engine, authorization, "printing:write")
    facility_id = _facility(engine, context, x_facility_id)
    try:
        row = LabelPrintingService(engine).claim_edge_job(context.organization_id, facility_id, job_id, f"service-account:{context.id}")
        return _job(row, include_content=True)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{job_id}/complete")
def complete_print_job(
    job_id: str,
    payload: PrintResult,
    authorization: str = Header(default=""),
    x_facility_id: str = Header(default="", alias="X-Facility-Id"),
    engine: Engine = Depends(get_engine),
):
    context = _ctx(engine, authorization, "printing:write")
    facility_id = _facility(engine, context, x_facility_id)
    try:
        row = LabelPrintingService(engine).complete_job(context.organization_id, facility_id, job_id, f"service-account:{context.id}", success=payload.success, error=payload.error)
        return _job(row)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
