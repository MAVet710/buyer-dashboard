"""Authenticated, facility-scoped telemetry boundary for manual and future adapters."""
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.audit import record_audit_event
from modules.coman.models import WorkItem
from modules.cultivation.models import CultivationRoom
from modules.cultivation.telemetry import Reading, TargetInput, TelemetryConflict, TelemetryService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..permissions import require_permission
from ..schemas.work import WorkCreate
from ..services.work import WorkService
from .plants import require_write

router = APIRouter(prefix="/inventory/production/plants/telemetry", tags=["cultivation"])


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[Reading] = Field(min_length=1, max_length=500)


def authorize_telemetry(context, engine, *, write=False, session=None):
    """Cultivation capability + legacy write role + facility permission override."""
    require_facility_capability(context, engine, "cultivation")
    if write:
        require_write(context)
        require_permission(context, engine, "cultivation.manage_telemetry", session=session)


def call(context, engine, room_id, method, *args, write=False):
    authorize_telemetry(context, engine, write=write)
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


@router.post("/rooms/{room_id}/exceptions/{exception_id}/work")
def create_environment_work(
    room_id: str,
    exception_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Create or return canonical Work for one current, server-derived exception."""
    authorize_telemetry(context, engine, write=True)
    service = TelemetryService(engine)
    try:
        with Session(engine) as session, session.begin():
            authorize_telemetry(context, engine, write=True, session=session)
            room = session.scalar(select(CultivationRoom).where(
                CultivationRoom.id == room_id,
                CultivationRoom.organization_id == context.organization_id,
                CultivationRoom.facility_id == context.facility_id,
            ).with_for_update())
            if room is None:
                raise LookupError("Room not found in the active facility.")
            draft = service.prepare_work_item(
                context.organization_id,
                context.facility_id,
                room_id,
                exception_id,
                actor=context.user_id,
                session=session,
            )
            existing = session.scalar(select(WorkItem).where(
                WorkItem.organization_id == context.organization_id,
                WorkItem.facility_id == context.facility_id,
                WorkItem.entity_type == "cultivation_telemetry_exception",
                WorkItem.entity_id == exception_id,
            ).order_by(WorkItem.created_at, WorkItem.id).limit(1).with_for_update())
            if existing is not None:
                return {"work_item_id": existing.id, "existing": True}
            evidence = {
                "room_id": room_id,
                "room_code": room.room_code,
                "exception_id": exception_id,
                "evidence_as_of": draft["evidence_as_of"],
                "telemetry": draft["evidence"],
                "decision_support_only": True,
            }
            item = WorkService(engine, context).create(WorkCreate(
                title=draft["title"],
                description="Review the current room environmental exception and document the operational response.",
                entity_type="cultivation_telemetry_exception",
                entity_id=exception_id,
                workspace="Cultivation",
                route=f"/cultivation?room={quote(room_id, safe='')}&telemetry={quote(exception_id, safe='')}",
                evidence=json.dumps(evidence, sort_keys=True, default=str),
            ), session=session)
            record_audit_event(
                session,
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                entity_type="cultivation_room",
                entity_id=room_id,
                action="environment_work_created",
                actor=context.user_id,
                source="api",
                correlation_id=item["id"],
                changes={"exception_id": exception_id, "work_item_id": item["id"]},
            )
            return {"work_item_id": item["id"], "existing": False}
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except TelemetryConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
