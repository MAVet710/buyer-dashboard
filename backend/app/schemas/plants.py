from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field

PlantPhase = Literal["clone", "seedling", "vegetative", "flowering", "harvested", "destroyed"]
HarvestStatus = Literal["planned", "active", "drying", "completed", "cancelled"]
CostType = Literal["labor", "material", "overhead"]
CostEntityType = Literal["plant", "harvest", "room"]

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

class CultivationRoomUpsert(BaseModel):
    room_code: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=255)
    phase: str = Field(default="", max_length=24)
    plant_capacity: int = Field(default=0, ge=0, le=1_000_000)
    square_feet: float = Field(default=0, ge=0)
    target_cycle_days: int = Field(default=0, ge=0, le=3650)
    active: bool = True
    notes: str = Field(default="", max_length=4000)

class CultivationHarvestCreate(BaseModel):
    harvest_code: str = Field(min_length=1, max_length=120)
    plant_ids: list[str] = Field(min_length=1, max_length=5000)
    notes: str = Field(default="", max_length=4000)

class CultivationHarvestTransition(BaseModel):
    status: HarvestStatus
    wet_weight: float | None = Field(default=None, ge=0)
    dry_weight: float | None = Field(default=None, ge=0)
    waste_weight: float | None = Field(default=None, ge=0)
    unit: str = Field(default="g", max_length=24)
    notes: str = Field(default="", max_length=4000)

class CultivationCostCreate(BaseModel):
    entity_type: CostEntityType
    entity_id: str = Field(min_length=1, max_length=64)
    cost_type: CostType
    description: str = Field(default="", max_length=255)
    quantity: float = Field(default=0, ge=0)
    unit: str = Field(default="", max_length=32)
    unit_cost: float = Field(default=0, ge=0)
    amount: float | None = Field(default=None, ge=0)
    occurred_on: date | None = None
    notes: str = Field(default="", max_length=4000)
