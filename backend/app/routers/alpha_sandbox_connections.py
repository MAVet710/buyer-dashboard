from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from modules.alpha_mode import AlphaOperatingModeService
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from .alpha_integrations_status import router as alpha_integrations_status_router
from .sandbox_integrations import (
    _PROVIDER_IDS,
    _public_provider,
    _require_developer_connections,
    _service,
)


router = APIRouter()
sandbox_router = APIRouter(prefix="/integrations/sandbox", tags=["integrations", "alpha"])


@sandbox_router.get("")
def alpha_aware_sandbox_connections(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Keep the DEV connection surface aligned with the selected alpha mode.

    The detailed Metrc setup card is intentionally omitted while DoobieLogic
    Sandbox is active. Other sandbox providers remain visible. Switching the
    facility to Metrc Sandbox makes the existing detailed Metrc card reappear
    without deleting or mutating any saved credentials.
    """

    _require_developer_connections(context)
    mode = AlphaOperatingModeService(engine).current(
        context.organization_id,
        context.facility_id,
    )
    service = _service(engine, settings)
    visible = [
        provider
        for provider in _PROVIDER_IDS
        if provider != "metrc" or mode.metrc_enabled
    ]
    return {
        "environment": "sandbox",
        "production_credentials_enabled": False,
        "production_writes_enabled": False,
        "organization_id": context.organization_id,
        "facility_id": context.facility_id,
        "scope": "facility",
        "alpha_operating_mode": mode.effective_mode,
        "providers": {
            provider: _public_provider(service, context, provider)
            for provider in visible
        },
    }


router.include_router(alpha_integrations_status_router)
router.include_router(sandbox_router)
