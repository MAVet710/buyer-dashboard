from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService
from services.doobie_connection import DEFAULT_DOOBIE_BASE_URL, test_doobie_connection
from services.metrc_client import test_metrc_connection
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_context import metrc_scope_key, resolve_metrc_context

router = APIRouter(prefix="/integrations", tags=["integrations"])


class MetrcSave(BaseModel):
    state: str = Field(default="", max_length=128)
    license_number: str = Field(default="", max_length=128)
    api_key: str | None = Field(default=None, max_length=1024)


class DoobieSave(BaseModel):
    base_url: str = Field(default=DEFAULT_DOOBIE_BASE_URL, max_length=1024)
    api_key: str | None = Field(default=None, max_length=1024)


def _service(engine: Engine, settings: Settings) -> IntegrationConfigurationService:
    try:
        return IntegrationConfigurationService(engine, settings.integration_encryption_key)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


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
    }
    if context.role == "dev":
        service = _service(engine, settings)
        result["doobie"] = service.public(service.get("platform", "global", "doobie"))
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


@router.post("/doobie")
def save_doobie(
    payload: DoobieSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role != "dev":
        raise HTTPException(403, "Level DEV access is required for platform AI settings.")
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
    if context.role != "dev":
        raise HTTPException(403, "Level DEV access is required for platform AI settings.")
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
