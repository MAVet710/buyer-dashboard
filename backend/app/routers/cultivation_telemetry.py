"""Authenticated, facility-scoped telemetry boundary for manual and future adapters."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine

from modules.cultivation.telemetry import Reading, TargetInput, TelemetryConflict, TelemetryService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from .plants import require_write

router = APIRouter(prefix="/inventory/production/plants/telemetry", tags=["cultivation"])


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[Reading] = Field(min_length=1, max_length=500)


def call(context, engine, room_id, method, *args, write=False):
    require_facility_capability(context, engine, "cultivation")
    if write:
        require_write(context)
    try:
        kwargs = {"actor": context.user_id} if write else {}
        return getattr(TelemetryService(engine), method)(context.organization_id, context.facility_id, room_id, *args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except TelemetryConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/rooms/{room_id}")
def room_environment(room_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return call(context, engine, room_id, "snapshot")


@router.post("/rooms/{room_id}/observations")
def ingest_environment(room_id: str, payload: IngestRequest, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return call(context, engine, room_id, "ingest", payload.observations, write=True)


@router.post("/rooms/{room_id}/target")
def configure_environment(room_id: str, payload: TargetInput, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return call(context, engine, room_id, "set_target", payload, write=True)
