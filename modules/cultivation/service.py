from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import InventoryLot, utc_now
from .models import (
    CultivationCostEntry,
    CultivationHarvest,
    CultivationHarvestPlant,
    CultivationPlant,
    CultivationPlantEvent,
    CultivationRoom,
)


TRANSITIONS = {
    "clone": {"seedling", "vegetative", "destroyed"},
    "seedling": {"vegetative", "destroyed"},
    "vegetative": {"flowering", "destroyed"},
    "flowering": {"harvested", "destroyed"},
    "harvested": set(), "destroyed": set(),
}
HARVEST_TRANSITIONS = {
    "planned": {"active", "cancelled"},
    "active": {"drying", "finished", "cancelled"},
    "drying": {"finished", "cancelled"},
    "finished": set(),
    "cancelled": set(),
}
ACTIVE_PLANT_PHASES = {"clone", "seedling", "vegetative", "flowering"}
OPEN_HARVEST_STATUSES = {"planned", "active", "drying"}
COST_TYPES = {"labor", "material", "overhead"}
COST_ENTITY_TYPES = {"plant", "harvest", "room"}


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

    def list_rooms(self, organization_id: str, facility_id: str) -> list[dict]:
        with self.sessions() as session:
            rooms = list(session.scalars(select(CultivationRoom).where(CultivationRoom.organization_id == organization_id, CultivationRoom.facility_id == facility_id).order_by(CultivationRoom.room_code)))
            plants = list(session.scalars(select(CultivationPlant).where(CultivationPlant.organization_id == organization_id, CultivationPlant.facility_id == facility_id, CultivationPlant.phase.in_(ACTIVE_PLANT_PHASES))))
            costs = list(session.scalars(select(CultivationCostEntry).where(CultivationCostEntry.organization_id == organization_id, CultivationCostEntry.facility_id == facility_id, CultivationCostEntry.entity_type == "room")))
        plants_by_room = Counter(plant.room_code for plant in plants)
        phases_by_room: dict[str, Counter] = {}
        next_harvest: dict[str, date] = {}
        for plant in plants:
            phases_by_room.setdefault(plant.room_code, Counter())[plant.phase] += 1
            if plant.estimated_harvest_date and (plant.room_code not in next_harvest or plant.estimated_harvest_date < next_harvest[plant.room_code]):
                next_harvest[plant.room_code] = plant.estimated_harvest_date
        cost_by_room = Counter()
        for row in costs:
            cost_by_room[row.entity_id] += float(row.amount or 0)
        return [self._room_payload(room, plants_by_room.get(room.room_code, 0), phases_by_room.get(room.room_code, Counter()), next_harvest.get(room.room_code), cost_by_room.get(room.id, 0.0)) for room in rooms]

    def upsert_room(self, organization_id: str, facility_id: str, *, room_code: str, display_name: str = "", phase: str = "", plant_capacity: int = 0, square_feet: float = 0, target_cycle_days: int = 0, active: bool = True, notes: str = "") -> dict:
        code = room_code.strip()
        normalized_phase = phase.strip().casefold()
        if not code: raise ValueError("Room code is required.")
        if normalized_phase and normalized_phase not in TRANSITIONS: raise ValueError("Room phase must be a supported cultivation phase.")
        if plant_capacity < 0 or square_feet < 0 or target_cycle_days < 0: raise ValueError("Room capacity, square feet and cycle days cannot be negative.")
        with self.sessions.begin() as session:
            room = session.scalar(select(CultivationRoom).where(CultivationRoom.organization_id == organization_id, CultivationRoom.facility_id == facility_id, CultivationRoom.room_code == code))
            if room is None:
                room = CultivationRoom(organization_id=organization_id, facility_id=facility_id, room_code=code)
                session.add(room)
            room.display_name = display_name.strip() or code
            room.phase = normalized_phase
            room.plant_capacity = int(plant_capacity)
            room.square_feet = float(square_feet)
            room.target_cycle_days = int(target_cycle_days)
            room.active = bool(active)
            room.notes = notes.strip()
            session.flush()
            room_id = room.id
        return next(row for row in self.list_rooms(organization_id, facility_id) if row["id"] == room_id)

    def list_harvests(self, organization_id: str, facility_id: str) -> list[dict]:
        with self.sessions() as session:
            harvests = list(session.scalars(select(CultivationHarvest).where(CultivationHarvest.organization_id == organization_id, CultivationHarvest.facility_id == facility_id).order_by(CultivationHarvest.planned_date.desc(), CultivationHarvest.created_at.desc())))
            links = list(session.scalars(select(CultivationHarvestPlant).where(CultivationHarvestPlant.organization_id == organization_id, CultivationHarvestPlant.facility_id == facility_id)))
            costs = list(session.scalars(select(CultivationCostEntry).where(CultivationCostEntry.organization_id == organization_id, CultivationCostEntry.facility_id == facility_id, CultivationCostEntry.entity_type == "harvest")))
        plant_counts = Counter(link.harvest_id for link in links)
        costs_by_harvest: dict[str, list[CultivationCostEntry]] = {}
        for cost in costs: costs_by_harvest.setdefault(cost.entity_id, []).append(cost)
        return [self._harvest_payload(row, plant_counts.get(row.id, 0), costs_by_harvest.get(row.id, [])) for row in harvests]

    def harvest_detail(self, organization_id: str, facility_id: str, harvest_id: str) -> dict:
        with self.sessions() as session:
            harvest = session.get(CultivationHarvest, harvest_id)
            if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id: raise ValueError("Harvest was not found in the active facility.")
            links = list(session.scalars(select(CultivationHarvestPlant).where(CultivationHarvestPlant.harvest_id == harvest.id)))
            plant_ids = [link.plant_id for link in links]
            plants = list(session.scalars(select(CultivationPlant).where(CultivationPlant.id.in_(plant_ids or ["__none__"]))))
            costs = list(session.scalars(select(CultivationCostEntry).where(CultivationCostEntry.organization_id == organization_id, CultivationCostEntry.facility_id == facility_id, CultivationCostEntry.entity_type == "harvest", CultivationCostEntry.entity_id == harvest.id).order_by(CultivationCostEntry.occurred_on, CultivationCostEntry.id)))
        return self._harvest_payload(harvest, len(links), costs) | {
            "plants": [self._plant_payload(row) for row in plants],
            "cost_entries": [self._cost_payload(row) for row in costs],
        }

    def create_harvest(self, organization_id: str, facility_id: str, *, harvest_code: str, plant_ids: list[str], actor: str, planned_date: date | None = None, notes: str = "") -> dict:
        code = harvest_code.strip()
        unique_ids = list(dict.fromkeys(str(value).strip() for value in plant_ids if str(value).strip()))
        if not code: raise ValueError("Harvest code is required.")
        if not unique_ids: raise ValueError("Select at least one flowering plant for the harvest.")
        with self.sessions.begin() as session:
            if session.scalar(select(CultivationHarvest.id).where(CultivationHarvest.facility_id == facility_id, CultivationHarvest.harvest_code == code)):
                raise ValueError("That harvest code already exists in the active facility.")
            plants = list(session.scalars(select(CultivationPlant).where(CultivationPlant.id.in_(unique_ids), CultivationPlant.organization_id == organization_id, CultivationPlant.facility_id == facility_id)))
            if len(plants) != len(unique_ids): raise ValueError("One or more selected plants were not found in the active facility.")
            invalid = [plant.plant_tag for plant in plants if plant.phase != "flowering"]
            if invalid: raise ValueError(f"Only flowering plants can be assigned to a harvest: {', '.join(invalid[:5])}.")
            existing = list(session.execute(select(CultivationHarvestPlant, CultivationHarvest).join(CultivationHarvest, CultivationHarvest.id == CultivationHarvestPlant.harvest_id).where(CultivationHarvestPlant.plant_id.in_(unique_ids), CultivationHarvest.status.in_(OPEN_HARVEST_STATUSES))).all())
            if existing: raise ValueError("One or more selected plants are already assigned to an open harvest.")
            strains = {plant.strain_name for plant in plants if plant.strain_name}
            rooms = {plant.room_code for plant in plants if plant.room_code}
            harvest = CultivationHarvest(organization_id=organization_id, facility_id=facility_id, harvest_code=code, strain_name=next(iter(strains)) if len(strains) == 1 else "Mixed", room_code=next(iter(rooms)) if len(rooms) == 1 else "Mixed", planned_date=planned_date, notes=notes.strip(), created_by=actor)
            session.add(harvest); session.flush()
            for plant in plants:
                session.add(CultivationHarvestPlant(organization_id=organization_id, facility_id=facility_id, harvest_id=harvest.id, plant_id=plant.id, assigned_by=actor))
                session.add(CultivationPlantEvent(organization_id=organization_id, facility_id=facility_id, plant_id=plant.id, event_type="harvest_assigned", to_value=harvest.harvest_code, reason="Assigned to planned harvest", notes=notes.strip(), actor=actor))
            session.flush()
            harvest_id = harvest.id
        return self.harvest_detail(organization_id, facility_id, harvest_id)

    def transition_harvest(self, organization_id: str, facility_id: str, harvest_id: str, *, status: str, actor: str, wet_weight: float | None = None, dry_weight: float | None = None, waste_weight: float | None = None, unit: str = "", notes: str = "") -> dict:
        target = status.strip().casefold()
        with self.sessions.begin() as session:
            harvest = session.get(CultivationHarvest, harvest_id)
            if not harvest or harvest.organization_id != organization_id or harvest.facility_id != facility_id: raise ValueError("Harvest was not found in the active facility.")
            if target != harvest.status and target not in HARVEST_TRANSITIONS.get(harvest.status, set()): raise ValueError(f"Harvest cannot move from {harvest.status} to {target}.")
            for value, label in ((wet_weight, "wet weight"), (dry_weight, "dry weight"), (waste_weight, "waste weight")):
                if value is not None and float(value) < 0: raise ValueError(f"Harvest {label} cannot be negative.")
            if wet_weight is not None: harvest.wet_weight = float(wet_weight)
            if dry_weight is not None: harvest.dry_weight = float(dry_weight)
            if waste_weight is not None: harvest.waste_weight = float(waste_weight)
            if unit.strip(): harvest.unit = unit.strip()
            if notes.strip(): harvest.notes = notes.strip()
            prior = harvest.status
            if target != prior:
                harvest.status = target
                if target == "active":
                    harvest.started_at = harvest.started_at or utc_now()
                    links = list(session.scalars(select(CultivationHarvestPlant).where(CultivationHarvestPlant.harvest_id == harvest.id)))
                    plants = list(session.scalars(select(CultivationPlant).where(CultivationPlant.id.in_([link.plant_id for link in links] or ["__none__"]))))
                    for plant in plants:
                        if plant.phase == "flowering":
                            session.add(CultivationPlantEvent(organization_id=organization_id, facility_id=facility_id, plant_id=plant.id, event_type="harvested", from_value="flowering", to_value=harvest.harvest_code, reason="Harvest started", notes=notes.strip(), actor=actor))
                            plant.phase = "harvested"
                            plant.retired_at = utc_now()
                if target == "finished": harvest.finished_at = harvest.finished_at or utc_now()
            session.flush()
        return self.harvest_detail(organization_id, facility_id, harvest_id)

    def add_cost(self, organization_id: str, facility_id: str, *, entity_type: str, entity_id: str, cost_type: str, actor: str, description: str = "", quantity: float = 0, unit: str = "", unit_cost: float = 0, amount: float | None = None, occurred_on: date | None = None, notes: str = "") -> dict:
        entity = entity_type.strip().casefold(); kind = cost_type.strip().casefold()
        if entity not in COST_ENTITY_TYPES: raise ValueError("Unsupported cultivation cost entity.")
        if kind not in COST_TYPES: raise ValueError("Cultivation cost type must be labor, material or overhead.")
        quantity = float(quantity or 0); unit_cost = float(unit_cost or 0)
        calculated = quantity * unit_cost if amount is None else float(amount)
        if quantity < 0 or unit_cost < 0 or calculated < 0: raise ValueError("Cultivation cost values cannot be negative.")
        with self.sessions.begin() as session:
            self._require_cost_entity(session, organization_id, facility_id, entity, entity_id)
            row = CultivationCostEntry(organization_id=organization_id, facility_id=facility_id, entity_type=entity, entity_id=entity_id, cost_type=kind, description=description.strip(), quantity=quantity, unit=unit.strip(), unit_cost=unit_cost, amount=calculated, occurred_on=occurred_on or date.today(), actor=actor, notes=notes.strip())
            session.add(row); session.flush()
            payload = self._cost_payload(row)
        return payload

    def _require_cost_entity(self, session, organization_id: str, facility_id: str, entity_type: str, entity_id: str) -> None:
        model = {"plant": CultivationPlant, "harvest": CultivationHarvest, "room": CultivationRoom}[entity_type]
        row = session.get(model, entity_id)
        if not row or row.organization_id != organization_id or row.facility_id != facility_id: raise ValueError(f"Cultivation {entity_type} was not found in the active facility.")

    @staticmethod
    def _plant_payload(plant: CultivationPlant) -> dict:
        return {"id": plant.id, "plant_tag": plant.plant_tag, "strain_name": plant.strain_name, "phase": plant.phase, "room_code": plant.room_code, "estimated_harvest_date": plant.estimated_harvest_date.isoformat() if plant.estimated_harvest_date else None}

    @staticmethod
    def _cost_payload(row: CultivationCostEntry) -> dict:
        return {"id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id, "cost_type": row.cost_type, "description": row.description, "quantity": float(row.quantity or 0), "unit": row.unit, "unit_cost": round(float(row.unit_cost or 0), 4), "amount": round(float(row.amount or 0), 2), "occurred_on": row.occurred_on.isoformat(), "actor": row.actor, "notes": row.notes}

    @staticmethod
    def _room_payload(room: CultivationRoom, active_plants: int, phases: Counter, next_harvest: date | None, total_cost: float) -> dict:
        capacity = int(room.plant_capacity or 0)
        utilization = (active_plants / capacity * 100) if capacity else 0.0
        phase_mismatch = sum(count for phase, count in phases.items() if room.phase and phase != room.phase)
        return {"id": room.id, "room_code": room.room_code, "display_name": room.display_name or room.room_code, "phase": room.phase, "plant_capacity": capacity, "active_plants": active_plants, "capacity_remaining": max(0, capacity - active_plants) if capacity else None, "utilization_pct": round(utilization, 1), "over_capacity": bool(capacity and active_plants > capacity), "phase_mismatch_count": phase_mismatch, "phase_counts": dict(phases), "square_feet": float(room.square_feet or 0), "target_cycle_days": int(room.target_cycle_days or 0), "next_estimated_harvest": next_harvest.isoformat() if next_harvest else None, "total_cost_usd": round(float(total_cost or 0), 2), "active": bool(room.active), "notes": room.notes}

    @classmethod
    def _harvest_payload(cls, harvest: CultivationHarvest, plant_count: int, costs: list[CultivationCostEntry]) -> dict:
        by_type = Counter()
        for cost in costs: by_type[cost.cost_type] += float(cost.amount or 0)
        total = sum(by_type.values())
        wet = float(harvest.wet_weight or 0); dry = float(harvest.dry_weight or 0); waste = float(harvest.waste_weight or 0)
        return {"id": harvest.id, "harvest_code": harvest.harvest_code, "strain_name": harvest.strain_name, "room_code": harvest.room_code, "status": harvest.status, "planned_date": harvest.planned_date.isoformat() if harvest.planned_date else None, "started_at": harvest.started_at.isoformat() if harvest.started_at else None, "finished_at": harvest.finished_at.isoformat() if harvest.finished_at else None, "plant_count": plant_count, "wet_weight": wet, "dry_weight": dry, "waste_weight": waste, "unit": harvest.unit, "dry_yield_pct": round((dry / wet * 100), 2) if wet > 0 else None, "labor_cost_usd": round(by_type.get("labor", 0.0), 2), "material_cost_usd": round(by_type.get("material", 0.0), 2), "overhead_cost_usd": round(by_type.get("overhead", 0.0), 2), "total_cogs_usd": round(total, 2), "cost_per_dry_unit": round(total / dry, 4) if dry > 0 else None, "notes": harvest.notes, "created_by": harvest.created_by}
