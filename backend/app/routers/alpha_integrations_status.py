from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from modules.alpha_mode import AlphaOperatingModeService
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_context import resolve_metrc_context
from .integrations import integrations as legacy_integrations


router = APIRouter(prefix="/integrations", tags=["integrations", "alpha"])


@router.get("")
def alpha_aware_integrations(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Preserve the existing integration payload while making mode authoritative."""

    result = legacy_integrations(context=context, engine=engine, settings=settings)
    mode = AlphaOperatingModeService(engine).current(
        context.organization_id,
        context.facility_id,
    )
    _, metrc = resolve_metrc_context(engine, settings, context)
    result["alpha_operating_mode"] = mode.public()
    result["metrc"] = {
        **result["metrc"],
        "status": metrc.status,
        "message": metrc.message,
        "environment": metrc.environment,
        "operating_mode": mode.effective_mode,
        "provider_operations_enabled": bool(mode.metrc_enabled and metrc.configured),
    }
    return result
