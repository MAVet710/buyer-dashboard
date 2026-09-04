from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.alpha_mode import AlphaOperatingModeService
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from .alpha_integrations_status import router as alpha_integrations_status_router
from .sandbox_integrations import (
    MetrcFacilityConfirm,
    MetrcFacilitySync,
    SandboxSyncRequest,
    _PROVIDER_IDS,
    _public_provider,
    _require_developer_connections,
    _service,
    bootstrap_metrc_sandbox_facility as legacy_bootstrap_metrc_sandbox_facility,
    confirm_metrc_sandbox_facility as legacy_confirm_metrc_sandbox_facility,
    discover_metrc_sandbox_facilities as legacy_discover_metrc_sandbox_facilities,
    provision_metrc_sandbox_user as legacy_provision_metrc_sandbox_user,
    retry_sandbox_sync as legacy_retry_sandbox_sync,
    run_sandbox_sync as legacy_run_sandbox_sync,
)


router = APIRouter()
sandbox_router = APIRouter(prefix="/integrations/sandbox", tags=["integrations", "alpha"])


def _require_metrc_alpha_mode(context: RequestContext, engine: Engine) -> None:
    mode = AlphaOperatingModeService(engine).current(
        context.organization_id,
        context.facility_id,
    )
    if not mode.metrc_enabled:
        raise HTTPException(
            409,
            "DoobieLogic Sandbox is active. Select Metrc Sandbox before provisioning, discovering, or syncing Metrc provider data.",
        )


@sandbox_router.get("")
def alpha_aware_sandbox_connections(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Keep the DEV connection surface aligned with the selected alpha mode."""

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


@sandbox_router.post("/metrc/provision-user")
def alpha_provision_metrc_sandbox_user(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_metrc_alpha_mode(context, engine)
    return legacy_provision_metrc_sandbox_user(context=context, engine=engine, settings=settings)


@sandbox_router.post("/metrc/discover-facilities")
def alpha_discover_metrc_sandbox_facilities(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_metrc_alpha_mode(context, engine)
    return legacy_discover_metrc_sandbox_facilities(context=context, engine=engine, settings=settings)


@sandbox_router.post("/metrc/facilities/confirm")
def alpha_confirm_metrc_sandbox_facility(
    payload: MetrcFacilityConfirm,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_metrc_alpha_mode(context, engine)
    return legacy_confirm_metrc_sandbox_facility(
        payload,
        context=context,
        engine=engine,
        settings=settings,
    )


@sandbox_router.post("/metrc/facilities/bootstrap")
def alpha_bootstrap_metrc_sandbox_facility(
    payload: MetrcFacilitySync,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_metrc_alpha_mode(context, engine)
    return legacy_bootstrap_metrc_sandbox_facility(
        payload,
        context=context,
        engine=engine,
        settings=settings,
    )


@sandbox_router.post("/metrc/sync")
def alpha_run_metrc_sandbox_sync(
    payload: SandboxSyncRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_metrc_alpha_mode(context, engine)
    return legacy_run_sandbox_sync(
        "metrc",
        payload,
        context=context,
        engine=engine,
        settings=settings,
    )


@sandbox_router.post("/metrc/retry")
def alpha_retry_metrc_sandbox_sync(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_metrc_alpha_mode(context, engine)
    return legacy_retry_sandbox_sync(
        "metrc",
        context=context,
        engine=engine,
        settings=settings,
    )


router.include_router(alpha_integrations_status_router)
router.include_router(sandbox_router)
