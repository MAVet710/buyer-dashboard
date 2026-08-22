from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from modules.cultivation.service import CultivationService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..schemas.plants import PlantCreate, PlantEventItem, PlantItem, PlantTransition

router = APIRouter(prefix="/inventory/production/plants", tags=["cultivation"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}

def item(plant) -> PlantItem:
    return PlantItem.model_validate({column: getattr(plant, column) for column in PlantItem.model_fields})

def require_write(context: RequestContext):
    if context.role.casefold() not in WRITE_ROLES: raise HTTPException(403, "Your role does not allow cultivation changes.")

def require_cultivation(context: RequestContext, engine: Engine):
    require_facility_capability(context, engine, "production")
    require_facility_capability(context, engine, "cultivation")

@router.get("", response_model=list[PlantItem])
def list_plants(phase: str = "", room: str = "", search: str = Query(default="", max_length=200), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_cultivation(context, engine)
    return [item(row) for row in CultivationService(engine).list_plants(context.organization_id, context.facility_id, phase, room, search)]

@router.post("", response_model=PlantItem, status_code=201)
def create_plant(payload: PlantCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_write(context)
    require_cultivation(context, engine)
    try: return item(CultivationService(engine).create_plant(context.organization_id, context.facility_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/{plant_id}/transition", response_model=PlantItem)
def transition_plant(plant_id: str, payload: PlantTransition, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_write(context)
    require_cultivation(context, engine)
    try: return item(CultivationService(engine).transition(context.organization_id, context.facility_id, plant_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.get("/{plant_id}/events", response_model=list[PlantEventItem])
def plant_events(plant_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_cultivation(context, engine)
    try:
        return [PlantEventItem.model_validate({column: getattr(row, column) for column in PlantEventItem.model_fields}) for row in CultivationService(engine).events(context.organization_id, context.facility_id, plant_id)]
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
