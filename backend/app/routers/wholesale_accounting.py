from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.wholesale_accounting import WholesaleAccountingService
from ..auth import RequestContext, get_commercial_context, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine


router = APIRouter(
    prefix="/commercial/accounting",
    tags=["commercial", "accounting"],
    dependencies=[Depends(get_commercial_context)],
)


@router.get("")
def wholesale_accounting_snapshot(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    try:
        return WholesaleAccountingService(engine, settings.integration_encryption_key).snapshot(
            context.organization_id,
            context.facility_id,
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
