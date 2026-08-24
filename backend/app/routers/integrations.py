from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService
from services.doobie_connection import DEFAULT_DOOBIE_BASE_URL, test_doobie_connection
from services.metrc_client import test_metrc_connection
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.ai_runtime import diagnostics
from ..services.metrc_context import metrc_scope_key, resolve_metrc_context
from ..services.spacemail import resolve_spacemail_settings, test_spacemail_connection

router = APIRouter(prefix="/integrations", tags=["integrations"])


class MetrcSave(BaseModel):
    state: str = Field(default="", max_length=128)
    license_number: str = Field(default="", max_length=128)
    api_key: str | None = Field(default=None, max_length=1024)


class DoobieSave(BaseModel):
    base_url: str = Field(default=DEFAULT_DOOBIE_BASE_URL, max_length=1024)
    api_key: str | None = Field(default=None, max_length=1024)


class SpacemailSave(BaseModel):
    smtp_username: str = Field(default="nelson@doobielogic.io", max_length=320)
    from_email: str = Field(default="support@doobielogic.io", max_length=320)
    from_name: str = Field(default="DoobieLogic Support", max_length=255)
    support_email: str = Field(default="support@doobielogic.io", max_length=320)
    help_email: str = Field(default="help@doobielogic.io", max_length=320)
    info_email: str = Field(default="info@doobielogic.io", max_length=320)
    welcome_email_enabled: bool = True
    mailbox_password: str | None = Field(default=None, max_length=2048)

    @field_validator("smtp_username", "from_email", "support_email", "help_email", "info_email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("from_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Sender name is required.")
        return normalized


class AIRuntimeSave(BaseModel):
    local_llm_base_url: str = Field(default="", max_length=1024)
    local_llm_model: str = Field(default="", max_length=255)
    local_embedding_base_url: str = Field(default="", max_length=1024)
    local_embedding_model: str = Field(default="", max_length=255)
    provider_mode: str = Field(default="local_first", max_length=40)
    provider_order: str = Field(default="local,gemini,openai,doobie", max_length=255)
    allow_cloud_fallback: bool = True
    api_key: str | None = Field(default=None, max_length=2048)

    @field_validator("provider_mode")
    @classmethod
    def valid_mode(cls, value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized not in {"local_first", "local_only"}:
            raise ValueError("Provider mode must be local_first or local_only.")
        return normalized

    @field_validator("provider_order")
    @classmethod
    def valid_order(cls, value: str) -> str:
        allowed = {"local", "gemini", "openai", "doobie"}
        names = [item.strip().casefold() for item in str(value or "").split(",") if item.strip()]
        if not names or any(name not in allowed for name in names):
            raise ValueError("Provider order may contain only local, gemini, openai, and doobie.")
        return ",".join(dict.fromkeys(names))


def _service(engine: Engine, settings: Settings) -> IntegrationConfigurationService:
    try:
        return IntegrationConfigurationService(engine, settings.integration_encryption_key)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


def _require_dev(context: RequestContext) -> None:
    if context.role != "dev":
        raise HTTPException(403, "Level DEV access is required for platform integration settings.")


@router.get("")
def integrations(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    try:
        metrc_service, metrc_context = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    result = {
        "metrc": {
            **metrc_service.public(metrc_context.row),
            "facility_id": context.facility_id,
            "facility_scoped": True,
        },
        "doobie": None,
        "ai_runtime": None,
        "spacemail": None,
    }
    if context.role == "dev":
        service = _service(engine, settings)
        result["doobie"] = service.public(service.get("platform", "global", "doobie"))
        result["ai_runtime"] = service.public(service.get("platform", "global", "ai_runtime"))
        result["spacemail"] = service.public(service.get("platform", "global", "spacemail"))
    return result


@router.post("/metrc")
def save_metrc(
    payload: MetrcSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    service = _service(engine, settings)
    row = service.save(
        scope_type="user",
        scope_key=metrc_scope_key(context),
        provider="metrc",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration={"state": payload.state.strip(), "license_number": payload.license_number.strip()},
        secret=payload.api_key,
        actor=context.user_id,
    )
    return {**service.public(row), "facility_id": context.facility_id, "facility_scoped": True}


@router.post("/metrc/test")
def test_metrc(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    try:
        service, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not metrc.row:
        raise HTTPException(422, "Save METRC settings for this facility before testing the connection.")
    try:
        result = test_metrc_connection(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            license_number=metrc.license_number,
        )
    except Exception as exc:
        result = {"ok": False, "message": str(exc)}
    updated = service.validation_result(
        metrc.row.id,
        ok=bool(result.get("ok")),
        error="" if result.get("ok") else str(result.get("message") or "Connection failed"),
    )
    return {
        **service.public(updated),
        "facility_id": context.facility_id,
        "facility_scoped": True,
        "result": {key: result.get(key) for key in ("ok", "message", "facility_count", "license_found")},
    }


@router.post("/metrc/clear")
def clear_metrc(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    service = _service(engine, settings)
    service.clear(
        scope_type="user",
        scope_key=metrc_scope_key(context),
        provider="metrc",
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return {**service.public(None), "facility_id": context.facility_id, "facility_scoped": True}


@router.post("/doobie")
def save_doobie(
    payload: DoobieSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    row = service.save(
        scope_type="platform",
        scope_key="global",
        provider="doobie",
        organization_id=None,
        facility_id=None,
        configuration={"base_url": payload.base_url.strip().rstrip("/")},
        secret=payload.api_key,
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return service.public(row)


@router.post("/doobie/test")
def test_doobie(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    row = service.get("platform", "global", "doobie")
    if not row:
        raise HTTPException(422, "Save Doobie settings before testing the connection.")
    config = service.public(row)["configuration"]
    try:
        result = test_doobie_connection(config.get("base_url", DEFAULT_DOOBIE_BASE_URL), service.secret(row))
    except Exception as exc:
        result = {"ok": False, "message": str(exc)}
    updated = service.validation_result(
        row.id,
        ok=bool(result.get("ok")),
        error="" if result.get("ok") else str(result.get("message") or "Connection failed"),
    )
    return {**service.public(updated), "result": {"ok": bool(result.get("ok")), "message": result.get("message")}}


@router.post("/doobie/clear")
def clear_doobie(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    service.clear(
        scope_type="platform",
        scope_key="global",
        provider="doobie",
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return service.public(None)


@router.post("/spacemail")
def save_spacemail(
    payload: SpacemailSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    existing = service.get("platform", "global", "spacemail")
    if not existing and not payload.mailbox_password and not settings.spacemail_smtp_password:
        raise HTTPException(422, "Enter the primary Spacemail mailbox password before saving.")
    row = service.save(
        scope_type="platform",
        scope_key="global",
        provider="spacemail",
        organization_id=None,
        facility_id=None,
        configuration={
            "smtp_username": payload.smtp_username,
            "from_email": payload.from_email,
            "from_name": payload.from_name,
            "support_email": payload.support_email,
            "help_email": payload.help_email,
            "info_email": payload.info_email,
            "welcome_email_enabled": bool(payload.welcome_email_enabled),
        },
        secret=payload.mailbox_password,
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return service.public(row)


@router.post("/spacemail/test")
def test_spacemail(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    row = service.get("platform", "global", "spacemail")
    mail_settings = resolve_spacemail_settings(engine, settings)
    if not row and not mail_settings.spacemail_is_configured:
        raise HTTPException(422, "Save Spacemail settings before testing the connection.")
    result = test_spacemail_connection(mail_settings)
    if row:
        updated = service.validation_result(
            row.id,
            ok=bool(result.get("ok")),
            error="" if result.get("ok") else str(result.get("message") or "Connection failed"),
        )
        public = service.public(updated)
    else:
        public = {"configured": True, "status": "connected" if result.get("ok") else "failed", "secret_hint": "environment", "configuration": {}, "last_validated_at": None, "last_error": "" if result.get("ok") else str(result.get("message") or "")}
    return {**public, "result": {"ok": bool(result.get("ok")), "message": result.get("message")}}


@router.post("/spacemail/clear")
def clear_spacemail(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    service.clear(
        scope_type="platform",
        scope_key="global",
        provider="spacemail",
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return service.public(None)


@router.post("/ai-runtime")
def save_ai_runtime(
    payload: AIRuntimeSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    row = service.save(
        scope_type="platform",
        scope_key="global",
        provider="ai_runtime",
        organization_id=None,
        facility_id=None,
        configuration={
            "local_llm_base_url": payload.local_llm_base_url.strip().rstrip("/"),
            "local_llm_model": payload.local_llm_model.strip(),
            "local_embedding_base_url": payload.local_embedding_base_url.strip().rstrip("/"),
            "local_embedding_model": payload.local_embedding_model.strip(),
            "provider_mode": payload.provider_mode,
            "provider_order": payload.provider_order,
            "allow_cloud_fallback": bool(payload.allow_cloud_fallback),
        },
        secret=payload.api_key,
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return service.public(row)


@router.post("/ai-runtime/test")
def test_ai_runtime(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    row = service.get("platform", "global", "ai_runtime")
    if not row:
        raise HTTPException(422, "Save Local AI Runtime settings before testing the connection.")
    result = diagnostics(engine=engine, settings=settings, context=context, operation_type="retail")
    local = (result.get("providers") or {}).get("local") or {}
    ok = bool(local.get("configured") and local.get("reachable"))
    updated = service.validation_result(row.id, ok=ok, error="" if ok else str(local.get("detail") or "Local model is not reachable."))
    return {
        **service.public(updated),
        "result": {
            "ok": ok,
            "message": "Local model is reachable." if ok else str(local.get("detail") or "Local model is not reachable."),
            "local": local,
            "embedding": result.get("embedding") or {},
            "knowledge": result.get("knowledge") or {},
            "provider_order": result.get("provider_order") or [],
            "cloud_fallback_enabled": bool(result.get("cloud_fallback_enabled")),
        },
    }


@router.post("/ai-runtime/clear")
def clear_ai_runtime(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_dev(context)
    service = _service(engine, settings)
    service.clear(
        scope_type="platform",
        scope_key="global",
        provider="ai_runtime",
        actor=context.user_id,
        audit_organization_id=context.organization_id,
        audit_facility_id=context.facility_id,
    )
    return service.public(None)
