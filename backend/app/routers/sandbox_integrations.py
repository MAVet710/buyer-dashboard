from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService, SandboxIntegrationRuntime
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/integrations/sandbox", tags=["integrations"])

_PROVIDER_IDS = {
    "metrc": "metrc_sandbox",
    "dutchie": "dutchie_sandbox",
    "biotrack": "biotrack_sandbox",
    "quickbooks": "quickbooks_sandbox",
}

_PROVIDER_SPECS = {
    "metrc": {
        "label": "METRC Sandbox",
        "auth_mode": "API key",
        "secret_label": "Sandbox user API key",
        "required": ("state", "license_number"),
        "allowed": ("state", "license_number", "base_url", "notes"),
        "resources": ("packages", "transfers", "items"),
        "future_use": "Traceability reads, guarded writes, reconciliation, package and transfer workflows.",
    },
    "dutchie": {
        "label": "Dutchie Sandbox",
        "auth_mode": "Developer credential",
        "secret_label": "Sandbox API key / developer secret",
        "required": ("location_id",),
        "allowed": ("location_id", "account_id", "client_id", "base_url", "notes"),
        "resources": ("sales", "inventory", "catalog"),
        "future_use": "Live inventory, catalog, sales, receiving and purchasing data ingestion.",
    },
    "biotrack": {
        "label": "BioTrack Sandbox",
        "auth_mode": "Username + password",
        "secret_label": "Sandbox password / API secret",
        "required": ("state", "license_number", "username"),
        "allowed": ("state", "license_number", "username", "base_url", "notes"),
        "resources": ("inventory", "transfers", "plants"),
        "future_use": "Provider-neutral traceability execution for BioTrack jurisdictions.",
    },
    "quickbooks": {
        "label": "QuickBooks Sandbox",
        "auth_mode": "OAuth 2.0",
        "secret_label": "Sandbox client secret",
        "required": ("client_id", "redirect_uri"),
        "allowed": ("client_id", "realm_id", "redirect_uri", "base_url", "notes"),
        "resources": ("invoices", "payments", "items"),
        "future_use": "Invoice, payment, COGS and accounting synchronization after OAuth authorization.",
    },
}


class SandboxConnectionSave(BaseModel):
    configuration: dict[str, str | bool] = Field(default_factory=dict)
    secret: str | None = Field(default=None, max_length=4096)


class SandboxSyncRequest(BaseModel):
    resource: str = Field(default="", max_length=64)


def _service(engine: Engine, settings: Settings) -> IntegrationConfigurationService:
    try:
        return IntegrationConfigurationService(engine, settings.integration_encryption_key)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


def _runtime(engine: Engine, settings: Settings) -> SandboxIntegrationRuntime:
    try:
        return SandboxIntegrationRuntime(engine, settings.integration_encryption_key)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


def _require_developer_connections(context: RequestContext) -> None:
    if context.role not in {"dev", "admin"}:
        raise HTTPException(403, "DEV or Admin access is required for developer connections.")


def _scope_key(context: RequestContext) -> str:
    return f"{context.organization_id}:{context.facility_id}:sandbox"


def _provider_spec(provider: str) -> tuple[str, dict]:
    normalized = str(provider or "").strip().casefold()
    provider_id = _PROVIDER_IDS.get(normalized)
    if not provider_id:
        raise HTTPException(404, "Unknown sandbox provider.")
    return provider_id, _PROVIDER_SPECS[normalized]


def _clean_configuration(provider: str, configuration: dict[str, str | bool]) -> dict[str, str | bool]:
    _, spec = _provider_spec(provider)
    allowed = set(spec["allowed"])
    unknown = sorted(set(configuration) - allowed)
    if unknown:
        raise HTTPException(422, f"Unsupported {provider} sandbox setting: {unknown[0]}")
    cleaned: dict[str, str | bool] = {"environment": "sandbox"}
    for key in spec["allowed"]:
        if key not in configuration:
            continue
        value = configuration[key]
        cleaned[key] = value if isinstance(value, bool) else str(value or "").strip()
    missing = [key for key in spec["required"] if not str(cleaned.get(key) or "").strip()]
    if missing:
        raise HTTPException(422, f"Missing required {provider} sandbox setting: {missing[0]}")
    return cleaned


def _public_provider(service: IntegrationConfigurationService, context: RequestContext, provider: str) -> dict:
    provider_id, spec = _provider_spec(provider)
    row = service.get("facility", _scope_key(context), provider_id)
    public = service.public(row)
    return {
        "provider": provider,
        "provider_id": provider_id,
        "label": spec["label"],
        "environment": "sandbox",
        "auth_mode": spec["auth_mode"],
        "secret_label": spec["secret_label"],
        "required_fields": list(spec["required"]),
        "allowed_fields": list(spec["allowed"]),
        "sandbox_resources": list(spec["resources"]),
        "future_use": spec["future_use"],
        "production_writes_enabled": False,
        **public,
    }


@router.get("")
def sandbox_connections(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_developer_connections(context)
    service = _service(engine, settings)
    return {
        "environment": "sandbox",
        "production_credentials_enabled": False,
        "production_writes_enabled": False,
        "organization_id": context.organization_id,
        "facility_id": context.facility_id,
        "scope": "facility",
        "providers": {
            provider: _public_provider(service, context, provider)
            for provider in _PROVIDER_IDS
        },
    }


@router.post("/{provider}")
def save_sandbox_connection(
    provider: str,
    payload: SandboxConnectionSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_developer_connections(context)
    provider_id, _ = _provider_spec(provider)
    service = _service(engine, settings)
    scope_key = _scope_key(context)
    existing = service.get("facility", scope_key, provider_id)
    if existing is None and not str(payload.secret or "").strip():
        raise HTTPException(422, "Enter the sandbox credential before saving this connection.")
    row = service.save(
        scope_type="facility",
        scope_key=scope_key,
        provider=provider_id,
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration=_clean_configuration(provider, payload.configuration),
        secret=payload.secret,
        actor=context.user_id,
    )
    return _public_provider(service, context, provider) | {"saved": True, "id": row.id}


@router.post("/{provider}/test")
def test_sandbox_connection(
    provider: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_developer_connections(context)
    provider_id, spec = _provider_spec(provider)
    service = _service(engine, settings)
    row = service.get("facility", _scope_key(context), provider_id)
    if row is None or not row.encrypted_secret:
        raise HTTPException(422, f"Save {spec['label']} credentials before testing readiness.")
    public = service.public(row)
    configuration = public.get("configuration") or {}
    missing = [key for key in spec["required"] if not str(configuration.get(key) or "").strip()]
    if missing:
        raise HTTPException(422, f"Sandbox configuration is incomplete: {missing[0]}")
    return {
        **_public_provider(service, context, provider),
        "result": {
            "ok": True,
            "configuration_ready": True,
            "connected": False,
            "verified": False,
            "environment": "sandbox",
            "message": (
                f"{spec['label']} configuration is complete and isolated to this facility. "
                "No live provider handshake was attempted. The sandbox runtime is ready to exercise durable reads, cursors, normalization, dedupe and reconciliation without external writes."
            ),
        },
    }


@router.get("/{provider}/runtime")
def sandbox_runtime_status(
    provider: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_developer_connections(context)
    _provider_spec(provider)
    try:
        return _runtime(engine, settings).status(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            provider=str(provider).strip().casefold(),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{provider}/sync")
def run_sandbox_sync(
    provider: str,
    payload: SandboxSyncRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_developer_connections(context)
    _provider_spec(provider)
    try:
        return _runtime(engine, settings).sync(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            provider=str(provider).strip().casefold(),
            actor=context.user_id,
            resource=payload.resource,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{provider}/retry")
def retry_sandbox_sync(
    provider: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_developer_connections(context)
    _provider_spec(provider)
    try:
        return _runtime(engine, settings).retry_failed(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            provider=str(provider).strip().casefold(),
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{provider}/clear")
def clear_sandbox_connection(
    provider: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_developer_connections(context)
    provider_id, _ = _provider_spec(provider)
    service = _service(engine, settings)
    service.clear(
        scope_type="facility",
        scope_key=_scope_key(context),
        provider=provider_id,
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return _public_provider(service, context, provider) | {"cleared": True}
