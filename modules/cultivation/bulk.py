"""Atomic bulk cultivation plant movement and phase changes."""

from __future__ import annotations

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import utc_now
from .models import CultivationPlant, CultivationPlantEvent, CultivationRoom
from .service import ACTIVE_PLANT_PHASES, TRANSITIONS


class CultivationBulkService:
    """Validate every selected plant and the destination before changing any row."""

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def transition(
        self,
        organization_id: str,
        facility_id: str,
        *,
        plant_ids: list[str],
        actor: str,
        phase: str | None = None,
        room_code: str | None = None,
        reason: str = "",
        notes: str = "",
    ) -> dict:
        ids = list(dict.fromkeys(str(value).strip() for value in plant_ids if str(value).strip()))
        target_phase = str(phase or "").strip().casefold()
        target_room = str(room_code or "").strip()
        reason = reason.strip()
        notes = notes.strip()
        if not ids:
            raise ValueError("Select at least one plant.")
        if len(ids) > 5000:
            raise ValueError("Bulk cultivation actions are limited to 5,000 plants at a time.")
        if not target_phase and not target_room:
            raise ValueError("Choose a phase and/or room change for the selected plants.")
        if target_phase and target_phase not in TRANSITIONS:
            raise ValueError("Unsupported plant phase.")

        with self.sessions.begin() as session:
            plants = list(
                session.scalars(
                    select(CultivationPlant)
                    .where(
                        CultivationPlant.id.in_(ids),
                        CultivationPlant.organization_id == organization_id,
                        CultivationPlant.facility_id == facility_id,
                    )
                    .with_for_update()
                )
            )
            if len(plants) != len(ids):
                raise ValueError("One or more selected plants were not found in the active cultivation facility.")

            by_id = {plant.id: plant for plant in plants}
            ordered = [by_id[plant_id] for plant_id in ids]
            final_phases: dict[str, str] = {}
            for plant in ordered:
                final_phase = target_phase or plant.phase
                if final_phase != plant.phase and final_phase not in TRANSITIONS.get(plant.phase, set()):
                    raise ValueError(f"Plant {plant.plant_tag} cannot move from {plant.phase} to {final_phase}.")
                final_phases[plant.id] = final_phase

            destination = None
            if target_room:
                destination = session.scalar(
                    select(CultivationRoom)
                    .where(
                        CultivationRoom.organization_id == organization_id,
                        CultivationRoom.facility_id == facility_id,
                        CultivationRoom.room_code == target_room,
                    )
                    .with_for_update()
                )
                if destination is None:
                    raise ValueError("Choose a configured cultivation room before moving selected plants.")
                if not destination.active:
                    raise ValueError(f"Cultivation room {target_room} is inactive.")
                incompatible = [
                    plant.plant_tag
                    for plant in ordered
                    if destination.phase and final_phases[plant.id] in ACTIVE_PLANT_PHASES and final_phases[plant.id] != destination.phase
                ]
                if incompatible:
                    raise ValueError(
                        f"Room {target_room} is configured for {destination.phase}; selected plant(s) would finish in a different active phase: "
                        + ", ".join(incompatible[:5])
                    )

                if destination.plant_capacity > 0:
                    selected_set = set(ids)
                    existing = int(
                        session.scalar(
                            select(func.count(CultivationPlant.id)).where(
                                CultivationPlant.organization_id == organization_id,
                                CultivationPlant.facility_id == facility_id,
                                CultivationPlant.room_code == target_room,
                                CultivationPlant.phase.in_(ACTIVE_PLANT_PHASES),
                                CultivationPlant.id.notin_(selected_set),
                            )
                        )
                        or 0
                    )
                    incoming_active = sum(final_phases[plant.id] in ACTIVE_PLANT_PHASES for plant in ordered)
                    projected = existing + incoming_active
                    if projected > destination.plant_capacity:
                        raise ValueError(
                            f"Room {target_room} capacity is {destination.plant_capacity}; this action would place {projected} active plants there."
                        )

            changed = 0
            for plant in ordered:
                final_phase = final_phases[plant.id]
                changed_plant = False
                if final_phase != plant.phase:
                    before = plant.phase
                    session.add(
                        CultivationPlantEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            plant_id=plant.id,
                            event_type="phase_changed",
                            from_value=before,
                            to_value=final_phase,
                            reason=reason,
                            notes=notes,
                            actor=actor,
                        )
                    )
                    plant.phase = final_phase
                    plant.retired_at = utc_now() if final_phase in {"harvested", "destroyed"} else None
                    changed_plant = True
                if target_room and target_room != plant.room_code:
                    before_room = plant.room_code
                    session.add(
                        CultivationPlantEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            plant_id=plant.id,
                            event_type="room_moved",
                            from_value=before_room,
                            to_value=target_room,
                            reason=reason,
                            notes=notes,
                            actor=actor,
                        )
                    )
                    plant.room_code = target_room
                    changed_plant = True
                if changed_plant:
                    changed += 1

            session.flush()
            return {
                "count": len(ordered),
                "changed_count": changed,
                "phase": target_phase or None,
                "room_code": target_room or None,
                "items": [
                    {
                        "id": plant.id,
                        "plant_tag": plant.plant_tag,
                        "strain_name": plant.strain_name,
                        "phase": plant.phase,
                        "room_code": plant.room_code,
                    }
                    for plant in ordered
                ],
            }
