from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import Engine

from ..auth import RequestContext, get_request_context
from ..database import get_engine
from ..schemas.inventory import InventoryAuditDetail, InventoryAuditScanCount
from ..services.audits import AuditService
from ..services.offline_audit_counts import IdempotentAuditCountService, OfflineMutationConflict
from .audits import _audit_for_operation, _validate


router = APIRouter(tags=["inventory-offline"])


@router.post("/{operation}/audits/{audit_id}/scan/count/replay", response_model=InventoryAuditDetail)
def replay_scanned_count(
    operation: str,
    audit_id: str,
    payload: InventoryAuditScanCount,
    idempotency_key: str = Header(default="", alias="X-Idempotency-Key"),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Apply one approved physical audit count exactly once.

    This is intentionally a local DoobieLogic inventory mutation. It never
    dispatches a regulatory/provider write. The idempotency receipt is committed
    in the same database transaction as the count so a lost response can be
    replayed safely with the same key.
    """

    _validate(operation, context, engine, True)
    audit_service = AuditService(engine)
    try:
        _audit_for_operation(audit_service, context, audit_id, operation)
        IdempotentAuditCountService(engine).record(
            context.organization_id,
            context.facility_id,
            audit_id,
            raw_code=payload.raw_code,
            quantity=payload.quantity,
            recount=payload.recount,
            reason=payload.reason,
            notes=payload.notes,
            actor=context.user_id,
            idempotency_key=idempotency_key,
        )
        return _audit_for_operation(audit_service, context, audit_id, operation)
    except OfflineMutationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
