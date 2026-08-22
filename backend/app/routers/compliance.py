from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Engine

from modules.traceability.backoffice import MANUAL_TRACEABILITY_ROLES, TraceabilityBackofficeRepository
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/compliance", tags=["compliance"])

class ManualResolution(BaseModel):
    action: str
    reason: str

def _item(row):
    return {key: getattr(row, key) for key in ("id", "provider", "license_number", "operation_type", "entity_type", "entity_id", "status", "external_reference", "error_code", "error_message", "attempt_count", "reason", "requested_by", "approved_by", "requested_at", "submitted_at", "completed_at")}

@router.get("/traceability")
def transactions(status: list[str] = Query(default=[]), provider: str = "", context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = TraceabilityBackofficeRepository(engine)
    return {"summary": repo.summary(context.organization_id, context.facility_id), "items": [_item(row) for row in repo.list_transactions(context.organization_id, context.facility_id, statuses=status, provider=provider)]}

@router.get("/traceability/{transaction_id}")
def detail(transaction_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = TraceabilityBackofficeRepository(engine)
    try:
        transaction = repo.get_transaction(context.organization_id, context.facility_id, transaction_id)
        events = repo.list_status_events(context.organization_id, context.facility_id, transaction_id)
        attempts = repo.list_attempts(context.organization_id, context.facility_id, transaction_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"transaction": _item(transaction), "events": [{key: getattr(row, key) for key in ("id", "from_status", "to_status", "actor", "reason", "source", "occurred_at")} for row in events], "attempts": [{key: getattr(row, key) for key in ("id", "attempt_number", "http_status", "error_code", "error_message", "started_at", "completed_at")} for row in attempts]}

@router.post("/traceability/{transaction_id}/resolve")
def resolve(transaction_id: str, payload: ManualResolution, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in MANUAL_TRACEABILITY_ROLES:
        raise HTTPException(403, "Your role does not allow manual compliance resolution.")
    repo = TraceabilityBackofficeRepository(engine)
    try:
        if payload.action == "requeue": row = repo.requeue_manual(organization_id=context.organization_id, facility_id=context.facility_id, transaction_id=transaction_id, actor=context.user_id, reason=payload.reason)
        elif payload.action == "verify": row = repo.verify_manual(organization_id=context.organization_id, facility_id=context.facility_id, transaction_id=transaction_id, actor=context.user_id, reason=payload.reason)
        elif payload.action == "cancel": row = repo.cancel_manual(organization_id=context.organization_id, facility_id=context.facility_id, transaction_id=transaction_id, actor=context.user_id, reason=payload.reason)
        else: raise HTTPException(422, "Action must be requeue, verify, or cancel.")
        return _item(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
