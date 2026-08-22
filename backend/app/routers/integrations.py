from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService
from services.doobie_config import DEFAULT_DOOBIE_BASE_URL, test_doobie_connection
from services.metrc_client import test_metrc_connection
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/integrations", tags=["integrations"])

class MetrcSave(BaseModel):
    state: str = Field(default="", max_length=128)
    license_number: str = Field(default="", max_length=128)
    api_key: str | None = Field(default=None, max_length=1024)

class DoobieSave(BaseModel):
    base_url: str = Field(default=DEFAULT_DOOBIE_BASE_URL, max_length=1024)
    api_key: str | None = Field(default=None, max_length=1024)

def _service(engine: Engine, settings: Settings) -> IntegrationConfigurationService:
    try: return IntegrationConfigurationService(engine, settings.integration_encryption_key)
    except RuntimeError as exc: raise HTTPException(503, str(exc)) from exc

@router.get("")
def integrations(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    service = _service(engine, settings); result = {"metrc": service.public(service.get("user", context.user_id, "metrc")), "doobie": None}
    if context.role == "dev": result["doobie"] = service.public(service.get("platform", "global", "doobie"))
    return result

@router.post("/metrc")
def save_metrc(payload: MetrcSave, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    service = _service(engine, settings); row = service.save(scope_type="user", scope_key=context.user_id, provider="metrc", organization_id=context.organization_id, facility_id=context.facility_id, configuration={"state": payload.state.strip(), "license_number": payload.license_number.strip()}, secret=payload.api_key, actor=context.user_id); return service.public(row)

@router.post("/metrc/test")
def test_metrc(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    service = _service(engine, settings); row = service.get("user", context.user_id, "metrc")
    if not row: raise HTTPException(422, "Save METRC settings before testing the connection.")
    config = service.public(row)["configuration"]
    try: result = test_metrc_connection(state=config.get("state", ""), user_api_key=service.secret(row), integrator_api_key=settings.metrc_integrator_key, license_number=config.get("license_number", ""))
    except Exception as exc: result = {"ok": False, "message": str(exc)}
    updated = service.validation_result(row.id, ok=bool(result.get("ok")), error="" if result.get("ok") else str(result.get("message") or "Connection failed")); return {**service.public(updated), "result": {key: result.get(key) for key in ("ok", "message", "facility_count", "license_found")}}

@router.post("/doobie")
def save_doobie(payload: DoobieSave, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    if context.role != "dev": raise HTTPException(403, "Level DEV access is required for platform AI settings.")
    service = _service(engine, settings); row = service.save(scope_type="platform", scope_key="global", provider="doobie", organization_id=None, facility_id=None, configuration={"base_url": payload.base_url.strip().rstrip("/")}, secret=payload.api_key, actor=context.user_id, audit_organization_id=context.organization_id, audit_facility_id=context.facility_id); return service.public(row)

@router.post("/doobie/test")
def test_doobie(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    if context.role != "dev": raise HTTPException(403, "Level DEV access is required for platform AI settings.")
    service = _service(engine, settings); row = service.get("platform", "global", "doobie")
    if not row: raise HTTPException(422, "Save Doobie settings before testing the connection.")
    config = service.public(row)["configuration"]
    try: result = test_doobie_connection(config.get("base_url", DEFAULT_DOOBIE_BASE_URL), service.secret(row))
    except Exception as exc: result = {"ok": False, "message": str(exc)}
    updated = service.validation_result(row.id, ok=bool(result.get("ok")), error="" if result.get("ok") else str(result.get("message") or "Connection failed")); return {**service.public(updated), "result": {"ok": bool(result.get("ok")), "message": result.get("message")}}
