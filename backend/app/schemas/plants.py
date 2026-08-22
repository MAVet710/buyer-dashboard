from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel

PlantPhase = Literal["clone", "seedling", "vegetative", "flowering", "harvested", "destroyed"]

class PlantCreate(BaseModel):
    plant_tag: str
    strain_name: str
    phase: PlantPhase = "clone"
    room_code: str = "UNASSIGNED"
    source_lot_id: str | None = None
    mother_plant_tag: str = ""
    planted_at: date | None = None
    estimated_harvest_date: date | None = None
    notes: str = ""

class PlantTransition(BaseModel):
    phase: PlantPhase
    room_code: str | None = None
    reason: str = ""
    notes: str = ""

class PlantItem(BaseModel):
    id: str
    plant_tag: str
    strain_name: str
    phase: PlantPhase
    room_code: str
    source_lot_id: str | None
    mother_plant_tag: str
    planted_at: date | None
    estimated_harvest_date: date | None
    retired_at: datetime | None
    notes: str

class PlantEventItem(BaseModel):
    id: str
    event_type: str
    from_value: str
    to_value: str
    reason: str
    notes: str
    actor: str
    occurred_at: datetime
