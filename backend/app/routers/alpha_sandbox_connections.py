from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.alpha_mode import AlphaOperatingModeService
from services.metrc_client import fetch_metrc_resource
from services.metrc_facility_onboarding import DiscoveredMetrcFacility, MetrcFacilityOnboardingError
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from .alpha_integrations_status import router as alpha_integrations_status_router
from .sandbox_integrations import (
    MetrcFacilityConfirm,
    MetrcFacilitySync,
    SandboxSyncRequest,
    _PROVIDER_IDS,
    _metrc_rows,
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


def _configuration(row, service) -> dict:
    public = service.public(row)
    configuration = public.get("configuration") if isinstance(public, dict) else {}
    return dict(configuration) if isinstance(configuration, dict) else {}


def _provider_license(record: dict) -> str:
    try:
        return DiscoveredMetrcFacility.from_record(record).license_number.strip()
    except MetrcFacilityOnboardingError:
        return ""


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


@sandbox_router.post("/metrc/test")
def alpha_test_metrc_sandbox_connection(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Perform one GET-only Metrc facilities handshake with the exact scoped key pair.

    Unlike the generic sandbox readiness endpoint, this route proves the currently
    active facility's encrypted vendor/user credential pair against the normal MA
    sandbox API. It never mutates Metrc and it never falls back to process-global
    credentials.
    """

    _require_developer_connections(context)
    _require_metrc_alpha_mode(context, engine)
    service = _service(engine, settings)
    vendor, user = _metrc_rows(service, context)
    vendor_config = _configuration(vendor, service)
    user_config = _configuration(user, service)

    vendor_state = str(vendor_config.get("state") or "").strip().upper()
    user_state = str(user_config.get("state") or "").strip().upper()
    if vendor_state != "MA" or user_state != "MA":
        raise HTTPException(409, "The saved Metrc vendor and user credentials must both be scoped to Massachusetts before testing.")

    vendor_environment = str(vendor_config.get("environment") or "").strip().casefold()
    user_environment = str(user_config.get("environment") or "").strip().casefold()
    if vendor_environment != "sandbox" or user_environment != "sandbox":
        raise HTTPException(409, "The saved Metrc vendor and user credentials must both be sandbox-scoped before testing.")

    vendor_license = str(vendor_config.get("license_number") or "").strip()
    user_license = str(user_config.get("license_number") or "").strip()
    if vendor_license and user_license and vendor_license.casefold() != user_license.casefold():
        raise HTTPException(409, "The saved Metrc vendor and user credentials target different facility licenses.")
    license_number = user_license or vendor_license

    try:
        vendor_key = service.secret(vendor)
        user_key = service.secret(user)
    except RuntimeError as exc:
        raise HTTPException(422, "The saved Metrc credential pair could not be decrypted. Check the server encryption configuration; do not reset the keys.") from exc

    result = fetch_metrc_resource(
        state="MA",
        user_api_key=user_key,
        integrator_api_key=vendor_key,
        resource="facilities",
        environment="sandbox",
        timeout_seconds=20,
        max_attempts=1,
    )
    provider_http_status = int(result.get("http_status") or 0)
    records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
    matched_facility_count = sum(
        1
        for record in records
        if license_number and _provider_license(record).casefold() == license_number.casefold()
    )
    connected = bool(result.get("ok") and provider_http_status == 200)
    license_mapping_verified = bool(license_number and matched_facility_count > 0)
    verified = bool(connected and (license_mapping_verified if license_number else records))

    if connected and license_mapping_verified:
        message = "Metrc authenticated the exact facility-scoped vendor/user key pair and returned the configured sandbox license."
    elif connected and license_number:
        message = "Metrc authenticated the exact facility-scoped key pair, but the configured sandbox license was not present in the Facilities response. Refresh facility discovery before regulatory operations."
    elif connected:
        message = "Metrc authenticated the exact facility-scoped key pair. Discover and confirm a sandbox facility before regulatory operations."
    else:
        message = str(result.get("message") or "Metrc rejected the exact facility-scoped sandbox key pair.")

    return {
        **_public_provider(service, context, "metrc"),
        "result": {
            "ok": verified,
            "configuration_ready": True,
            "connected": connected,
            "verified": verified,
            "environment": "sandbox",
            "read_only": True,
            "network_request_sent": True,
            "provider_http_status": provider_http_status,
            "facility_count": len(records),
            "license_number": license_number,
            "matched_facility_count": matched_facility_count,
            "license_mapping_verified": license_mapping_verified,
            "message": message,
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