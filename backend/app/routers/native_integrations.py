"""Production-safe native provider control plane.

Provider credentials remain encrypted in IntegrationConfiguration. These routes
never treat a configured record as live until the provider-specific test has
succeeded, and they never expose decrypted credential material to the browser.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine

from modules.coman.repository import ComanRepository
from modules.integrations import IntegrationConfigurationService
from services.biotrack_client import test_biotrack_connection
from services.metrc_client import (
    fetch_metrc_delivery_packages,
    fetch_metrc_incoming_transfers,
    fetch_metrc_transfer_deliveries,
)
from services.quickbooks_client import test_quickbooks_connection
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_context import resolve_metrc_context

router = APIRouter(prefix="/native-integrations", tags=["native-integrations"])
ADMIN_ROLES = {"dev", "admin"}


def _require_admin(context: RequestContext) -> None:
    if context.role.casefold() not in ADMIN_ROLES:
        raise HTTPException(403, "Administrator access is required to change native provider credentials.")


def _service(engine: Engine, settings: Settings) -> IntegrationConfigurationService:
    try:
        return IntegrationConfigurationService(engine, settings.integration_encryption_key)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


def _scope(context: RequestContext) -> str:
    return context.facility_id


def _secret_json(service: IntegrationConfigurationService, row) -> dict[str, str]:
    if row is None or not row.encrypted_secret:
        return {}
    try:
        parsed = json.loads(service.secret(row))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "Stored provider credentials are unreadable.") from exc
    return {str(key): str(value) for key, value in parsed.items()} if isinstance(parsed, dict) else {}


def _safe_provider(service: IntegrationConfigurationService, provider: str, context: RequestContext) -> dict[str, Any]:
    public = service.public(service.get("facility", _scope(context), provider))
    return {**public, "provider": provider, "facility_id": context.facility_id, "facility_scoped": True}


class BioTrackSave(BaseModel):
    base_url: str = Field(min_length=8, max_length=1024)
    license_number: str = Field(min_length=1, max_length=160)
    username: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, max_length=2048)
    environment: Literal["sandbox", "production"] = "sandbox"
    login_path: str = Field(default="/v1/login", min_length=2, max_length=255)
    confirm_production: bool = False

    @field_validator("base_url")
    @classmethod
    def https_url(cls, value: str) -> str:
        clean = str(value or "").strip().rstrip("/")
        if not clean.casefold().startswith("https://"):
            raise ValueError("BioTrack base URL must use HTTPS.")
        return clean

    @field_validator("login_path")
    @classmethod
    def explicit_login_path(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean.startswith("/"):
            raise ValueError("BioTrack login path must start with '/'.")
        return clean


class QuickBooksSave(BaseModel):
    realm_id: str = Field(min_length=1, max_length=255)
    environment: Literal["sandbox", "production"] = "sandbox"
    client_id: str | None = Field(default=None, max_length=1024)
    client_secret: str | None = Field(default=None, max_length=2048)
    refresh_token: str | None = Field(default=None, max_length=4096)
    api_base_url: str = Field(default="", max_length=1024)
    token_url: str = Field(default="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", max_length=1024)
    confirm_production: bool = False

    @field_validator("api_base_url", "token_url")
    @classmethod
    def https_when_present(cls, value: str) -> str:
        clean = str(value or "").strip().rstrip("/")
        if clean and not clean.casefold().startswith("https://"):
            raise ValueError("QuickBooks URLs must use HTTPS.")
        return clean


@router.get("")
def native_integrations(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    service = _service(engine, settings)
    try:
        _metrc_service, metrc = resolve_metrc_context(engine, settings, context)
        metrc_public = service.public(metrc.row)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "metrc": {**metrc_public, "provider": "metrc", "facility_id": context.facility_id, "facility_scoped": True, "dispatch_operations": ["package_finish", "package_adjust"]},
        "biotrack": _safe_provider(service, "biotrack", context),
        "quickbooks": _safe_provider(service, "quickbooks", context),
        "activation_rules": {
            "metrc": "Validated user API key + integrator key + matching facility license.",
            "biotrack": "State-approved API access and an explicit state contract are required; sandbox/production are never inferred.",
            "quickbooks": "Intuit OAuth credentials and a validated company realm are required; rotated refresh tokens remain encrypted.",
        },
    }


@router.post("/biotrack")
def save_biotrack(
    payload: BioTrackSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    if payload.environment == "production" and not payload.confirm_production:
        raise HTTPException(422, "Production BioTrack activation requires explicit confirmation and approved provider credentials.")
    service = _service(engine, settings)
    current = service.get("facility", _scope(context), "biotrack")
    secrets = _secret_json(service, current)
    if payload.username is not None:
        secrets["username"] = payload.username.strip()
    if payload.password is not None:
        secrets["password"] = payload.password
    if not secrets.get("username") or not secrets.get("password"):
        raise HTTPException(422, "BioTrack username and password are required for the first save.")
    row = service.save(
        scope_type="facility",
        scope_key=_scope(context),
        provider="biotrack",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration={
            "base_url": payload.base_url,
            "license_number": payload.license_number.strip(),
            "environment": payload.environment,
            "login_path": payload.login_path,
        },
        secret=json.dumps(secrets, sort_keys=True),
        actor=context.user_id,
    )
    return _safe_provider(service, "biotrack", context)


@router.post("/biotrack/test")
def test_biotrack(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    service = _service(engine, settings)
    row = service.get("facility", _scope(context), "biotrack")
    if row is None:
        raise HTTPException(422, "Save BioTrack settings before testing.")
    config = service.public(row).get("configuration", {})
    secrets = _secret_json(service, row)
    result = test_biotrack_connection(
        base_url=str(config.get("base_url") or ""),
        username=secrets.get("username", ""),
        password=secrets.get("password", ""),
        license_number=str(config.get("license_number") or ""),
        training=str(config.get("environment") or "sandbox") != "production",
        login_path=str(config.get("login_path") or "/v1/login"),
    )
    updated = service.validation_result(row.id, ok=bool(result.get("ok")), error="" if result.get("ok") else str(result.get("message") or "Connection failed"))
    return {**service.public(updated), "provider": "biotrack", "facility_id": context.facility_id, "result": {"ok": bool(result.get("ok")), "message": result.get("message"), "training": result.get("training")}}


@router.post("/biotrack/clear")
def clear_biotrack(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    service = _service(engine, settings)
    service.clear(scope_type="facility", scope_key=_scope(context), provider="biotrack", actor=context.user_id, audit_organization_id=context.organization_id, audit_facility_id=context.facility_id)
    return _safe_provider(service, "biotrack", context)


@router.post("/quickbooks")
def save_quickbooks(
    payload: QuickBooksSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    if payload.environment == "production" and not payload.confirm_production:
        raise HTTPException(422, "Production QuickBooks activation requires explicit confirmation.")
    service = _service(engine, settings)
    current = service.get("facility", _scope(context), "quickbooks")
    secrets = _secret_json(service, current)
    for key, value in (("client_id", payload.client_id), ("client_secret", payload.client_secret), ("refresh_token", payload.refresh_token)):
        if value is not None:
            secrets[key] = value.strip()
    if not all(secrets.get(key) for key in ("client_id", "client_secret", "refresh_token")):
        raise HTTPException(422, "QuickBooks client ID, client secret, and refresh token are required for the first save.")
    row = service.save(
        scope_type="facility",
        scope_key=_scope(context),
        provider="quickbooks",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration={
            "realm_id": payload.realm_id.strip(),
            "environment": payload.environment,
            "api_base_url": payload.api_base_url,
            "token_url": payload.token_url,
        },
        secret=json.dumps(secrets, sort_keys=True),
        actor=context.user_id,
    )
    return _safe_provider(service, "quickbooks", context)


@router.post("/quickbooks/test")
def test_quickbooks(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    service = _service(engine, settings)
    row = service.get("facility", _scope(context), "quickbooks")
    if row is None:
        raise HTTPException(422, "Save QuickBooks settings before testing.")
    config = service.public(row).get("configuration", {})
    secrets = _secret_json(service, row)
    result = test_quickbooks_connection(
        client_id=secrets.get("client_id", ""),
        client_secret=secrets.get("client_secret", ""),
        refresh_token=secrets.get("refresh_token", ""),
        realm_id=str(config.get("realm_id") or ""),
        environment=str(config.get("environment") or "sandbox"),
        api_base_url=str(config.get("api_base_url") or ""),
        token_url=str(config.get("token_url") or "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"),
    )
    rotated = str(result.pop("refresh_token", secrets.get("refresh_token", "")) or "")
    if result.get("ok") and rotated and rotated != secrets.get("refresh_token"):
        secrets["refresh_token"] = rotated
        row = service.save(
            scope_type="facility",
            scope_key=_scope(context),
            provider="quickbooks",
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            configuration=dict(config),
            secret=json.dumps(secrets, sort_keys=True),
            actor=context.user_id,
        )
    updated = service.validation_result(row.id, ok=bool(result.get("ok")), error="" if result.get("ok") else str(result.get("message") or "Connection failed"))
    safe_result = {key: result.get(key) for key in ("ok", "message", "company")}
    return {**service.public(updated), "provider": "quickbooks", "facility_id": context.facility_id, "result": safe_result}


@router.post("/quickbooks/clear")
def clear_quickbooks(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_admin(context)
    service = _service(engine, settings)
    service.clear(scope_type="facility", scope_key=_scope(context), provider="quickbooks", actor=context.user_id, audit_organization_id=context.organization_id, audit_facility_id=context.facility_id)
    return _safe_provider(service, "quickbooks", context)


def _metrc_ready(engine: Engine, settings: Settings, context: RequestContext):
    try:
        _service_obj, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not metrc.configured or not metrc.row or metrc.status != "connected":
        raise HTTPException(409, "Validate the Metrc connection for this facility before loading live receiving data.")
    return metrc


@router.get("/metrc/incoming")
def metrc_incoming(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc_ready(engine, settings, context)
    result = fetch_metrc_incoming_transfers(state=metrc.state, user_api_key=metrc.user_api_key, integrator_api_key=metrc.integrator_api_key, license_number=metrc.license_number)
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or "Metrc incoming transfers request failed."))
    return {"provider": "metrc", "license_number": metrc.license_number, "transfers": result.get("transfers", [])}


@router.get("/metrc/transfers/{transfer_id}/deliveries")
def metrc_transfer_deliveries(
    transfer_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc_ready(engine, settings, context)
    result = fetch_metrc_transfer_deliveries(state=metrc.state, user_api_key=metrc.user_api_key, integrator_api_key=metrc.integrator_api_key, transfer_id=transfer_id)
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or "Metrc transfer delivery request failed."))
    return {"provider": "metrc", "transfer_id": transfer_id, "deliveries": result.get("deliveries", [])}


def _package_label(row: dict[str, Any]) -> str:
    return str(row.get("Label") or row.get("PackageLabel") or row.get("Tag") or row.get("label") or "").strip()


@router.get("/metrc/deliveries/{delivery_id}/packages")
def metrc_delivery_packages(
    delivery_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc_ready(engine, settings, context)
    result = fetch_metrc_delivery_packages(state=metrc.state, user_api_key=metrc.user_api_key, integrator_api_key=metrc.integrator_api_key, delivery_id=delivery_id)
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or "Metrc delivery package request failed."))
    packages = list(result.get("packages") or [])
    lots = ComanRepository(engine).list_inventory_lots(context.organization_id, context.facility_id)
    existing = {str(lot.compliance_package_id or "").strip() for lot in lots if str(lot.compliance_package_id or "").strip()}
    reconciled = []
    for package in packages:
        label = _package_label(package)
        reconciled.append({"package": package, "package_label": label, "inventory_status": "already_received" if label and label in existing else "new", "existing_inventory_match": bool(label and label in existing)})
    return {
        "provider": "metrc",
        "delivery_id": delivery_id,
        "package_count": len(reconciled),
        "already_received": sum(item["existing_inventory_match"] for item in reconciled),
        "new_packages": sum(not item["existing_inventory_match"] for item in reconciled),
        "packages": reconciled,
        "mutation_performed": False,
    }
