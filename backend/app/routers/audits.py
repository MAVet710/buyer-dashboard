from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from ..auth import RequestContext, get_request_context
from ..database import get_engine
from ..schemas.inventory import InventoryAuditComplete, InventoryAuditCounts, InventoryAuditCreate, InventoryAuditDetail, InventoryAuditStatusChange, InventoryAuditSummary
from ..services.audits import AuditService

router = APIRouter(prefix="/inventory/{operation}/audits", tags=["inventory-audits"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}


def _validate(operation: str, context: RequestContext, write: bool = False):
    if operation not in {"retail", "production"}:
        raise HTTPException(404, "Inventory operation not found.")
    if write and context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow inventory audit changes.")


@router.get("", response_model=list[InventoryAuditSummary])
def list_audits(operation: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context)
    return AuditService(engine).list(context.organization_id, context.facility_id, operation)


@router.post("", response_model=InventoryAuditSummary, status_code=201)
def create_audit(operation: str, payload: InventoryAuditCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, True)
    try: return AuditService(engine).create(context.organization_id, context.facility_id, operation, payload, context.user_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.get("/{audit_id}", response_model=InventoryAuditDetail)
def audit_detail(operation: str, audit_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context)
    try: return AuditService(engine).detail(context.organization_id, context.facility_id, audit_id)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc


@router.post("/{audit_id}/counts", response_model=InventoryAuditDetail)
def save_counts(operation: str, audit_id: str, payload: InventoryAuditCounts, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, True); service = AuditService(engine)
    try:
        service.repository.save_counts(context.organization_id, context.facility_id, audit_id, counts=[row.model_dump() for row in payload.counts], actor=context.user_id)
        return service.detail(context.organization_id, context.facility_id, audit_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/{audit_id}/status", response_model=InventoryAuditSummary)
def change_status(operation: str, audit_id: str, payload: InventoryAuditStatusChange, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, True)
    try: return AuditService(engine).status(context.organization_id, context.facility_id, audit_id, payload.status, context.user_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/{audit_id}/complete", response_model=InventoryAuditSummary)
def complete_audit(operation: str, audit_id: str, payload: InventoryAuditComplete, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _validate(operation, context, True); service = AuditService(engine)
    try: return service.summary(service.repository.complete_audit(context.organization_id, context.facility_id, audit_id, actor=context.user_id, post_adjustments=payload.post_adjustments))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
