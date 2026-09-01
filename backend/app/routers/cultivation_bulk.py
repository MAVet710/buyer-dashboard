from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.cultivation.bulk import CultivationBulkService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine

router = APIRouter(prefix="/inventory/production/plants", tags=["cultivation"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}
PlantPhase = Literal["clone", "seedling", "vegetative", "flowering", "harvested", "destroyed"]


class BulkPlantTransition(BaseModel):
    plant_ids: list[str] = Field(min_length=1, max_length=5000)
    phase: PlantPhase | None = None
    room_code: str | None = Field(default=None, max_length=120)
    reason: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=4000)


@router.post("/bulk-transition")
def bulk_transition_plants(
    payload: BulkPlantTransition,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow cultivation changes.")
    require_facility_capability(context, engine, "cultivation")
    if payload.phase is None and not str(payload.room_code or "").strip():
        raise HTTPException(422, "Choose a phase and/or room change for the selected plants.")
    try:
        return CultivationBulkService(engine).transition(
            context.organization_id,
            context.facility_id,
            actor=context.user_id,
            **payload.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
