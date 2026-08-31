from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import InventoryLot, utc_now

from .batch_models import CultivationPlantGroup, CultivationPlantGroupMember, CultivationPlantParentLink
from .models import CultivationPlant, CultivationPlantEvent, CultivationRoom
from .service import ACTIVE_PLANT_PHASES, TRANSITIONS


GROUP_TYPES = {"clone_batch", "seed_batch", "nursery", "vegetative", "flowering"}
GROUP_PHASE = {
    "clone_batch": "clone",
    "seed_batch": "seedling",
    "nursery": "clone",
    "vegetative": "vegetative",
    "flowering": "flowering",
}


class CultivationBatchService:
    """Atomic batch operations while preserving plant-level audit history."""

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _scope(session, organization_id: str, facility_id: str) -> None:
        from modules.coman.models import Facility

        facility = session.get(Facility, facility_id)
        if not facility or facility.organization_id != organization_id:
            raise ValueError("Cultivation facility was not found in the active organization.")
        if not bool(getattr(facility, "cultivation_enabled", False)):
            raise ValueError("The active facility is not enabled for cultivation.")

    @staticmethod
    def _mother(session, organization_id: str, facility_id: str, mother_plant_id: str | None) -> CultivationPlant | None:
        if not mother_plant_id:
            return None
        plant = session.get(CultivationPlant, mother_plant_id)
        if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id:
            raise ValueError("Mother/source plant was not found in the active cultivation facility.")
        if plant.phase in {"harvested", "destroyed"}:
            raise ValueError("A retired plant cannot be used as a new mother/source plant.")
        return plant

    @staticmethod
    def _source_lot(session, organization_id: str, facility_id: str, source_lot_id: str | None) -> InventoryLot | None:
        if not source_lot_id:
            return None
        lot = session.get(InventoryLot, source_lot_id)
        if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
            raise ValueError("Source lot/package was not found in the active cultivation facility.")
        return lot

    @staticmethod
    def _room_capacity(session, organization_id: str, facility_id: str, room_code: str, incoming: int, excluding_ids: set[str] | None = None) -> None:
        code = str(room_code or "UNASSIGNED").strip() or "UNASSIGNED"
        room = session.scalar(
            select(CultivationRoom).where(
                CultivationRoom.organization_id == organization_id,
                CultivationRoom.facility_id == facility_id,
                CultivationRoom.room_code == code,
                CultivationRoom.active.is_(True),
            )
        )
        if room is None or int(room.plant_capacity or 0) <= 0:
            return
        statement = select(func.count(CultivationPlant.id)).where(
            CultivationPlant.organization_id == organization_id,
            CultivationPlant.facility_id == facility_id,
            CultivationPlant.room_code == code,
            CultivationPlant.phase.in_(ACTIVE_PLANT_PHASES),
        )
        if excluding_ids:
            statement = statement.where(CultivationPlant.id.not_in(excluding_ids))
        current = int(session.scalar(statement) or 0)
        if current + int(incoming) > int(room.plant_capacity):
            raise ValueError(
                f"Room {code} capacity would be exceeded ({current + incoming}/{room.plant_capacity} plants)."
            )

    def create_group(
        self,
        organization_id: str,
        facility_id: str,
        *,
        group_code: str,
        group_type: str,
        strain_name: str,
        quantity: int,
        actor: str,
        room_code: str = "UNASSIGNED",
        mother_plant_id: str | None = None,
        source_lot_id: str | None = None,
        plant_tags: list[str] | None = None,
        tag_prefix: str = "",
        planted_at: date | None = None,
        estimated_harvest_date: date | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        code = str(group_code or "").strip()
        kind = str(group_type or "").strip().casefold()
        strain = str(strain_name or "").strip()
        room = str(room_code or "UNASSIGNED").strip() or "UNASSIGNED"
        qty = int(quantity)
        if not code or not strain:
            raise ValueError("Group code and strain are required.")
        if kind not in GROUP_TYPES:
            raise ValueError("Unsupported cultivation group type.")
        if qty < 1 or qty > 5000:
            raise ValueError("Cultivation groups must contain between 1 and 5,000 plants.")
        supplied = [str(value).strip() for value in (plant_tags or []) if str(value).strip()]
        if supplied and len(supplied) != qty:
            raise ValueError("When plant tags are supplied, provide exactly one tag per plant.")
        prefix = str(tag_prefix or code).strip().upper().replace(" ", "-")
        tags = supplied or [f"{prefix}-{index:04d}" for index in range(1, qty + 1)]
        if len(set(tag.casefold() for tag in tags)) != len(tags):
            raise ValueError("Plant tags in a cultivation group must be unique.")
        phase = GROUP_PHASE[kind]

        with self.sessions.begin() as session:
            self._scope(session, organization_id, facility_id)
            if session.scalar(
                select(CultivationPlantGroup.id).where(
                    CultivationPlantGroup.facility_id == facility_id,
                    func.lower(CultivationPlantGroup.group_code) == code.casefold(),
                )
            ):
                raise ValueError("That cultivation group code already exists in this facility.")
            existing = set(
                session.scalars(
                    select(CultivationPlant.plant_tag).where(
                        CultivationPlant.facility_id == facility_id,
                        func.lower(CultivationPlant.plant_tag).in_([tag.casefold() for tag in tags]),
                    )
                )
            )
            if existing:
                raise ValueError("One or more generated/supplied plant tags already exist in this facility.")
            mother = self._mother(session, organization_id, facility_id, mother_plant_id)
            self._source_lot(session, organization_id, facility_id, source_lot_id)
            if mother and mother.strain_name.casefold() != strain.casefold():
                raise ValueError("Mother/source plant strain must match the new cultivation group strain.")
            self._room_capacity(session, organization_id, facility_id, room, qty)

            group = CultivationPlantGroup(
                organization_id=organization_id,
                facility_id=facility_id,
                group_code=code,
                group_type=kind,
                strain_name=strain,
                room_code=room,
                source_lot_id=source_lot_id,
                mother_plant_id=mother.id if mother else None,
                status="active",
                created_by=str(actor or "system"),
                notes=str(notes or "").strip(),
            )
            session.add(group)
            session.flush()
            for tag in tags:
                plant = CultivationPlant(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    plant_tag=tag,
                    strain_name=strain,
                    phase=phase,
                    room_code=room,
                    source_lot_id=source_lot_id,
                    mother_plant_tag=mother.plant_tag if mother else "",
                    planted_at=planted_at,
                    estimated_harvest_date=estimated_harvest_date,
                    notes=str(notes or "").strip(),
                )
                session.add(plant)
                session.flush()
                session.add(
                    CultivationPlantGroupMember(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        group_id=group.id,
                        plant_id=plant.id,
                        added_by=actor,
                    )
                )
                if mother:
                    session.add(
                        CultivationPlantParentLink(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            child_plant_id=plant.id,
                            parent_plant_id=mother.id,
                            relationship="mother",
                            linked_by=actor,
                        )
                    )
                session.add(
                    CultivationPlantEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        plant_id=plant.id,
                        event_type="created_in_group",
                        to_value=phase,
                        reason=f"Created in cultivation group {code}",
                        notes=str(notes or "").strip(),
                        actor=actor,
                    )
                )
            group_id = group.id
        return self.group_detail(organization_id, facility_id, group_id)

    def list_groups(self, organization_id: str, facility_id: str, *, include_closed: bool = False) -> list[dict[str, Any]]:
        with self.sessions() as session:
            self._scope(session, organization_id, facility_id)
            statement = select(CultivationPlantGroup).where(
                CultivationPlantGroup.organization_id == organization_id,
                CultivationPlantGroup.facility_id == facility_id,
            )
            if not include_closed:
                statement = statement.where(CultivationPlantGroup.status == "active")
            groups = list(session.scalars(statement.order_by(CultivationPlantGroup.created_at.desc())))
            return [self._payload(session, row) for row in groups]

    def group_detail(self, organization_id: str, facility_id: str, group_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            self._scope(session, organization_id, facility_id)
            group = session.get(CultivationPlantGroup, group_id)
            if not group or group.organization_id != organization_id or group.facility_id != facility_id:
                raise ValueError("Cultivation group was not found in the active facility.")
            return self._payload(session, group, include_plants=True)

    def transition_group(
        self,
        organization_id: str,
        facility_id: str,
        group_id: str,
        *,
        actor: str,
        phase: str | None = None,
        room_code: str | None = None,
        reason: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        target = str(phase or "").strip().casefold()
        room = None if room_code is None else (str(room_code).strip() or "UNASSIGNED")
        with self.sessions.begin() as session:
            self._scope(session, organization_id, facility_id)
            group = session.get(CultivationPlantGroup, group_id)
            if not group or group.organization_id != organization_id or group.facility_id != facility_id:
                raise ValueError("Cultivation group was not found in the active facility.")
            if group.status != "active":
                raise ValueError("Closed cultivation groups cannot be changed.")
            members = list(
                session.scalars(
                    select(CultivationPlant)
                    .join(CultivationPlantGroupMember, CultivationPlantGroupMember.plant_id == CultivationPlant.id)
                    .where(CultivationPlantGroupMember.group_id == group.id)
                    .order_by(CultivationPlant.plant_tag)
                )
            )
            active = [plant for plant in members if plant.phase in ACTIVE_PLANT_PHASES]
            if not active:
                raise ValueError("This cultivation group has no active plants to change.")
            if target:
                invalid = [plant.plant_tag for plant in active if target != plant.phase and target not in TRANSITIONS.get(plant.phase, set())]
                if invalid:
                    raise ValueError(f"Batch transition is invalid for one or more plants: {', '.join(invalid[:5])}.")
            if room is not None:
                self._room_capacity(session, organization_id, facility_id, room, len(active), {row.id for row in active})

            for plant in active:
                if target and target != plant.phase:
                    before = plant.phase
                    plant.phase = target
                    if target in {"harvested", "destroyed"}:
                        plant.retired_at = utc_now()
                    session.add(
                        CultivationPlantEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            plant_id=plant.id,
                            event_type="phase_changed",
                            from_value=before,
                            to_value=target,
                            reason=str(reason or "").strip() or f"Batch action {group.group_code}",
                            notes=str(notes or "").strip(),
                            actor=actor,
                        )
                    )
                if room is not None and room != plant.room_code and plant.phase in ACTIVE_PLANT_PHASES:
                    before_room = plant.room_code
                    plant.room_code = room
                    session.add(
                        CultivationPlantEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            plant_id=plant.id,
                            event_type="room_moved",
                            from_value=before_room,
                            to_value=room,
                            reason=str(reason or "").strip() or f"Batch action {group.group_code}",
                            notes=str(notes or "").strip(),
                            actor=actor,
                        )
                    )
            if room is not None:
                group.room_code = room
            if target in {"vegetative", "flowering"}:
                group.group_type = target
            if target in {"harvested", "destroyed"}:
                group.status = "closed"
                group.closed_at = utc_now()
            session.flush()
        return self.group_detail(organization_id, facility_id, group_id)

    def plant_lineage(self, organization_id: str, facility_id: str, plant_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            self._scope(session, organization_id, facility_id)
            plant = session.get(CultivationPlant, plant_id)
            if not plant or plant.organization_id != organization_id or plant.facility_id != facility_id:
                raise ValueError("Plant was not found in the active facility.")
            membership = session.scalar(
                select(CultivationPlantGroupMember).where(CultivationPlantGroupMember.plant_id == plant.id)
            )
            group = session.get(CultivationPlantGroup, membership.group_id) if membership else None
            parent_link = session.scalar(
                select(CultivationPlantParentLink).where(
                    CultivationPlantParentLink.child_plant_id == plant.id,
                    CultivationPlantParentLink.relationship == "mother",
                )
            )
            mother = session.get(CultivationPlant, parent_link.parent_plant_id) if parent_link else None
            source_lot = session.get(InventoryLot, plant.source_lot_id) if plant.source_lot_id else None
            return {
                "plant_id": plant.id,
                "plant_tag": plant.plant_tag,
                "strain_name": plant.strain_name,
                "group": None if not group else {
                    "id": group.id,
                    "group_code": group.group_code,
                    "group_type": group.group_type,
                    "status": group.status,
                },
                "mother": None if not mother else {
                    "id": mother.id,
                    "plant_tag": mother.plant_tag,
                    "strain_name": mother.strain_name,
                    "phase": mother.phase,
                },
                "source_lot": None if not source_lot else {
                    "id": source_lot.id,
                    "lot_code": source_lot.lot_code,
                    "compliance_package_id": source_lot.compliance_package_id,
                },
            }

    @staticmethod
    def _payload(session, group: CultivationPlantGroup, *, include_plants: bool = False) -> dict[str, Any]:
        members = list(
            session.scalars(
                select(CultivationPlant)
                .join(CultivationPlantGroupMember, CultivationPlantGroupMember.plant_id == CultivationPlant.id)
                .where(CultivationPlantGroupMember.group_id == group.id)
                .order_by(CultivationPlant.plant_tag)
            )
        )
        phase_counts: dict[str, int] = {}
        for plant in members:
            phase_counts[plant.phase] = phase_counts.get(plant.phase, 0) + 1
        mother = session.get(CultivationPlant, group.mother_plant_id) if group.mother_plant_id else None
        payload: dict[str, Any] = {
            "id": group.id,
            "group_code": group.group_code,
            "group_type": group.group_type,
            "strain_name": group.strain_name,
            "room_code": group.room_code,
            "source_lot_id": group.source_lot_id,
            "mother_plant_id": group.mother_plant_id,
            "mother_plant_tag": mother.plant_tag if mother else "",
            "status": group.status,
            "plant_count": len(members),
            "active_plant_count": sum(plant.phase in ACTIVE_PLANT_PHASES for plant in members),
            "phase_counts": phase_counts,
            "notes": group.notes,
            "created_at": group.created_at,
            "closed_at": group.closed_at,
        }
        if include_plants:
            payload["plants"] = [
                {
                    "id": plant.id,
                    "plant_tag": plant.plant_tag,
                    "strain_name": plant.strain_name,
                    "phase": plant.phase,
                    "room_code": plant.room_code,
                    "source_lot_id": plant.source_lot_id,
                    "mother_plant_tag": plant.mother_plant_tag,
                    "estimated_harvest_date": plant.estimated_harvest_date,
                }
                for plant in members
            ]
        return payload
