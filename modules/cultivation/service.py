from __future__ import annotations

from datetime import date

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import InventoryLot, utc_now
from .models import CultivationPlant, CultivationPlantEvent


TRANSITIONS = {
    "clone": {"seedling", "vegetative", "destroyed"},
    "seedling": {"vegetative", "destroyed"},
    "vegetative": {"flowering", "destroyed"},
    "flowering": {"harvested", "destroyed"},
    "harvested": set(), "destroyed": set(),
}


class CultivationService:
    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def list_plants(self, organization_id: str, facility_id: str, phase: str = "", room: str = "", search: str = ""):
        with self.sessions() as session:
            statement = select(CultivationPlant).where(CultivationPlant.organization_id == organization_id, CultivationPlant.facility_id == facility_id)
            if phase: statement = statement.where(CultivationPlant.phase == phase)
            if room: statement = statement.where(CultivationPlant.room_code == room)
            plants = list(session.scalars(statement.order_by(CultivationPlant.phase, CultivationPlant.room_code, CultivationPlant.plant_tag)))
        needle = search.strip().casefold()
        return [plant for plant in plants if not needle or needle in f"{plant.plant_tag} {plant.strain_name} {plant.room_code} {plant.mother_plant_tag}".casefold()]

    def create_plant(self, organization_id: str, facility_id: str, *, plant_tag: str, strain_name: str, phase: str, room_code: str, actor: str, source_lot_id: str | None = None, mother_plant_tag: str = "", planted_at: date | None = None, estimated_harvest_date: date | None = None, notes: str = ""):
        tag = plant_tag.strip(); phase = phase.strip().casefold()
        if not tag or not strain_name.strip(): raise ValueError("Plant tag and strain are required.")
        if phase not in TRANSITIONS: raise ValueError("Unsupported plant phase.")
        with self.sessions.begin() as session:
            if session.scalar(select(CultivationPlant.id).where(CultivationPlant.facility_id == facility_id, CultivationPlant.plant_tag == tag)):
                raise ValueError("That plant tag already exists in the active facility.")
            if source_lot_id:
                lot = session.get(InventoryLot, source_lot_id)
                if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id: raise ValueError("Source package was not found in the active facility.")
            plant = CultivationPlant(organization_id=organization_id, facility_id=facility_id, plant_tag=tag, strain_name=strain_name.strip(), phase=phase, room_code=room_code.strip() or "UNASSIGNED", source_lot_id=source_lot_id, mother_plant_tag=mother_plant_tag.strip(), planted_at=planted_at, estimated_harvest_date=estimated_harvest_date, notes=notes.strip())
            session.add(plant); session.flush()
            session.add(CultivationPlantEvent(organization_id=organization_id, facility_id=facility_id, plant_id=plant.id, event_type="created", to_value=phase, actor=actor, notes=notes.strip()))
        return plant

    def transition(self, organization_id: str, facility_id: str, plant_id: str, *, phase: str, room_code: str | None, actor: str, reason: str = "", notes: str = ""):
        target = phase.strip().casefold()
        with self.sessions.begin() as session:
            plant = session.get(CultivationPlant, plant_id)
            if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id: raise ValueError("Plant was not found in the active facility.")
            if target != plant.phase:
                if target not in TRANSITIONS.get(plant.phase, set()): raise ValueError(f"Plant cannot move from {plant.phase} to {target}.")
                session.add(CultivationPlantEvent(organization_id=organization_id, facility_id=facility_id, plant_id=plant.id, event_type="phase_changed", from_value=plant.phase, to_value=target, reason=reason.strip(), notes=notes.strip(), actor=actor))
                plant.phase = target
                if target in {"harvested", "destroyed"}: plant.retired_at = utc_now()
            if room_code is not None and room_code.strip() and room_code.strip() != plant.room_code:
                session.add(CultivationPlantEvent(organization_id=organization_id, facility_id=facility_id, plant_id=plant.id, event_type="room_moved", from_value=plant.room_code, to_value=room_code.strip(), reason=reason.strip(), notes=notes.strip(), actor=actor))
                plant.room_code = room_code.strip()
        return plant

    def events(self, organization_id: str, facility_id: str, plant_id: str):
        with self.sessions() as session:
            plant = session.get(CultivationPlant, plant_id)
            if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id: raise ValueError("Plant was not found in the active facility.")
            return list(session.scalars(select(CultivationPlantEvent).where(CultivationPlantEvent.plant_id == plant_id).order_by(CultivationPlantEvent.occurred_at)))
