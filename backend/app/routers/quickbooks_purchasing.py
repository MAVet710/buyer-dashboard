from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.quickbooks_purchasing import QuickBooksPurchasingSyncService
from services.quickbooks_sync import QuickBooksSyncError
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine


router = APIRouter(prefix="/native-integrations/quickbooks", tags=["native-integrations", "accounting"])
ADMIN_ROLES = {"dev", "admin"}


def _require_admin(context: RequestContext) -> None:
    if context.role.casefold() not in ADMIN_ROLES:
        raise HTTPException(403, "Administrator access is required for QuickBooks synchronization.")


def _service(engine: Engine, settings: Settings) -> QuickBooksPurchasingSyncService:
    try:
        return QuickBooksPurchasingSyncService(engine, settings.integration_encryption_key)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/vendors/{partner_id}/sync")
def sync_quickbooks_vendor(
    partner_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    try:
        return _service(engine, settings).sync_vendor(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            partner_id=partner_id,
            actor=context.user_id,
        )
    except QuickBooksSyncError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/purchase-orders/{order_id}/sync")
def sync_quickbooks_purchase_order(
    order_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    try:
        return _service(engine, settings).sync_purchase_order(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            order_id=order_id,
            actor=context.user_id,
        )
    except QuickBooksSyncError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/reconciliation")
def quickbooks_purchasing_reconciliation(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    return _service(engine, settings).reconciliation_snapshot(
        context.organization_id,
        context.facility_id,
    )
