from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Mapping

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, Facility, utc_now
from modules.cultivation.batch_models import CultivationPlantGroup, CultivationPlantGroupMember
from modules.cultivation.models import CultivationPlant, CultivationRoom
from modules.operational_moats.models import CultivationHarvest
from modules.traceability.object_links import TraceabilityObjectLink


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = record.get("source")
    return nested if isinstance(nested, Mapping) else record


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _nested_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("Name") or value.get("name") or value.get("Label") or value.get("label"))
    if isinstance(value, (list, tuple, set)):
        values = [_nested_name(item) for item in value]
        values = [item for item in values if item]
        if not values:
            return ""
        unique = list(dict.fromkeys(values))
        return unique[0] if len(unique) == 1 else "Mixed"
    return _text(value)


def _provider_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    return _text(record.get("provider_id") or _first(source, "Id", "ID", "id", "ExternalId"))


def _provider_label(record: Mapping[str, Any], *source_keys: str) -> str:
    source = _source(record)
    return _text(record.get("label") or record.get("name") or _first(source, *source_keys, "Label", "Name"))


def _strain(record: Mapping[str, Any]) -> str:
    source = _source(record)
    return _nested_name(
        _first(
            source,
            "StrainName",
            "strainName",
            "SourceStrainNames",
            "sourceStrainNames",
            "Strain",
            "strain",
        )
        or record.get("name")
    )


def _location_ref(record: Mapping[str, Any]) -> tuple[str, str]:
    source = _source(record)
    nested = _first(source, "Location", "location", "DryingLocation", "dryingLocation")
    nested_id = ""
    nested_name = ""
    if isinstance(nested, Mapping):
        nested_id = _text(nested.get("Id") or nested.get("id"))
        nested_name = _text(nested.get("Name") or nested.get("name"))
    provider_id = _text(
        _first(
            source,
            "LocationId",
            "locationId",
            "CurrentLocationId",
            "currentLocationId",
            "DryingLocationId",
            "dryingLocationId",
            "HarvestLocationId",
            "harvestLocationId",
        )
        or nested_id
    )
    name = _text(
        _first(
            source,
            "LocationName",
            "locationName",
            "CurrentLocationName",
            "currentLocationName",
            "DryingLocationName",
            "dryingLocationName",
            "HarvestLocationName",
            "harvestLocationName",
        )
        or nested_name
    )
    return provider_id, name


def _plant_batch_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    nested = _first(source, "PlantBatch", "plantBatch")
    if isinstance(nested, Mapping):
        nested_id = nested.get("Id") or nested.get("id")
    else:
        nested_id = None
    return _text(
        _first(source, "PlantBatchId", "plantBatchId", "SourcePlantBatchId", "sourcePlantBatchId")
        or nested_id
    )


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _integer(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_code(preferred: str, *, prefix: str, provider_id: str, limit: int = 120) -> str:
    value = _text(preferred)
    if value and len(value) <= limit:
        return value
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", _text(provider_id)).strip("-") or "OBJECT"
    return f"{prefix}-{token}"[:limit]


def _group_type(record: Mapping[str, Any]) -> str:
    source = _source(record)
    raw = _text(
        _first(source, "Type", "type", "PlantBatchType", "plantBatchType", "PlantBatchTypeName", "TypeName")
    ).casefold()
    if "seed" in raw:
        return "seed_batch"
    if "clone" in raw:
        return "clone_batch"
    if "veget" in raw:
        return "vegetative"
    if "flower" in raw:
        return "flowering"
    return "nursery"


def _harvest_strain(record: Mapping[str, Any]) -> str:
    source = _source(record)
    return _nested_name(
        _first(source, "SourceStrainNames", "sourceStrainNames", "StrainName", "strainName", "Strain", "strain")
    )


class MetrcCultivationMaterializer:
    """Seed existing provider-owned cultivation state without fabricating history.

    Exact provider IDs and regulatory plant tags establish identity. Existing local
    operational values are never silently rewritten. Mutable names can label newly
    seeded objects, but are never used to rebind an existing local object to Metrc.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def seed(
        self,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        actor: str,
        locations: list[dict[str, Any]],
        plant_batches: list[dict[str, Any]],
        vegetative_plants: list[dict[str, Any]],
        flowering_plants: list[dict[str, Any]],
        harvests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = _text(state).upper()
        environment = _text(environment).casefold()
        license_number = _text(license_number)
        actor = _text(actor) or "system"
        if not state or environment not in {"sandbox", "production"} or not license_number:
            raise ValueError("Cultivation hydration requires exact jurisdiction, environment, and facility license scope.")

        counters = {
            "created_rooms": 0,
            "created_groups": 0,
            "created_plants": 0,
            "created_harvests": 0,
            "created_group_memberships": 0,
            "created_links": 0,
            "existing_linked_objects": 0,
        }
        conflicts: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        def conflict(code: str, provider_id: str, message: str) -> None:
            conflicts.append({"code": code, "provider_id": provider_id, "message": message})

        def warning(code: str, provider_id: str, message: str) -> None:
            warnings.append({"code": code, "provider_id": provider_id, "message": message})

        with self.sessions.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("Cultivation hydration facility does not belong to the organization.")

            links = list(session.scalars(select(TraceabilityObjectLink).where(
                TraceabilityObjectLink.organization_id == organization_id,
                TraceabilityObjectLink.facility_id == facility_id,
                TraceabilityObjectLink.provider == "metrc",
                TraceabilityObjectLink.environment == environment,
            )))
            provider_links = {(row.provider_resource, row.provider_id): row for row in links}
            local_links = {(row.entity_type, row.entity_id): row for row in links}

            rooms = list(session.scalars(select(CultivationRoom).where(
                CultivationRoom.organization_id == organization_id,
                CultivationRoom.facility_id == facility_id,
            )))
            rooms_by_id = {row.id: row for row in rooms}
            rooms_by_code = {_text(row.room_code).casefold(): row for row in rooms}

            groups = list(session.scalars(select(CultivationPlantGroup).where(
                CultivationPlantGroup.organization_id == organization_id,
                CultivationPlantGroup.facility_id == facility_id,
            )))
            groups_by_id = {row.id: row for row in groups}
            groups_by_code = {_text(row.group_code).casefold(): row for row in groups}

            plants = list(session.scalars(select(CultivationPlant).where(
                CultivationPlant.organization_id == organization_id,
                CultivationPlant.facility_id == facility_id,
            )))
            plants_by_id = {row.id: row for row in plants}
            plants_by_tag = {_text(row.plant_tag).casefold(): row for row in plants}

            local_harvests = list(session.scalars(select(CultivationHarvest).where(
                CultivationHarvest.organization_id == organization_id,
                CultivationHarvest.facility_id == facility_id,
            )))
            harvests_by_id = {row.id: row for row in local_harvests}
            harvests_by_code = {_text(row.harvest_code).casefold(): row for row in local_harvests}

            def existing_provider_link(resource: str, provider_id: str, entity_type: str):
                link = provider_links.get((resource, provider_id))
                if link is None:
                    return None
                if link.license_number != license_number or link.jurisdiction != state:
                    conflict(
                        "provider_identity_scope_mismatch",
                        provider_id,
                        "The exact Metrc identity is already linked under a different jurisdiction/license scope.",
                    )
                    return False
                if link.entity_type != entity_type:
                    conflict(
                        "provider_identity_collision",
                        provider_id,
                        "The exact Metrc identity is already linked to a different DoobieLogic object type.",
                    )
                    return False
                return link

            def add_link(*, entity_type: str, entity_id: str, resource: str, provider_id: str, label: str) -> bool:
                provider_existing = provider_links.get((resource, provider_id))
                local_existing = local_links.get((entity_type, entity_id))
                if provider_existing is not None and (
                    provider_existing.entity_type != entity_type or provider_existing.entity_id != entity_id
                ):
                    conflict("provider_identity_collision", provider_id, "The provider object is already linked to another local object.")
                    return False
                if local_existing is not None and (
                    local_existing.provider_resource != resource or local_existing.provider_id != provider_id
                ):
                    conflict("local_identity_collision", provider_id, "The local object is already linked to a different provider identity.")
                    return False
                row = provider_existing or local_existing
                now = utc_now()
                if row is None:
                    row = TraceabilityObjectLink(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        provider="metrc",
                        jurisdiction=state,
                        environment=environment,
                        license_number=license_number,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        provider_resource=resource,
                        provider_id=provider_id,
                        provider_label=_text(label)[:255],
                        status="verified",
                        mismatch_reason="",
                        verified_at=now,
                        last_seen_at=now,
                    )
                    session.add(row)
                    session.flush()
                    provider_links[(resource, provider_id)] = row
                    local_links[(entity_type, entity_id)] = row
                    counters["created_links"] += 1
                else:
                    if row.license_number != license_number or row.jurisdiction != state:
                        conflict("identity_scope_mismatch", provider_id, "Existing regulatory identity belongs to another license scope.")
                        return False
                    row.provider_label = _text(label)[:255] or row.provider_label
                    row.status = "verified"
                    row.mismatch_reason = ""
                    row.verified_at = now
                    row.last_seen_at = now
                    counters["existing_linked_objects"] += 1
                return True

            cultivation_records = [
                *[row for row in plant_batches if isinstance(row, dict)],
                *[row for row in vegetative_plants if isinstance(row, dict)],
                *[row for row in flowering_plants if isinstance(row, dict)],
                *[row for row in harvests if isinstance(row, dict)],
            ]
            referenced_location_ids = {
                location_id
                for row in cultivation_records
                for location_id, _name in [_location_ref(row)]
                if location_id
            }
            location_by_provider_id: dict[str, CultivationRoom] = {}

            for record in locations:
                if not isinstance(record, dict):
                    continue
                provider_id = _provider_id(record)
                if not provider_id or provider_id not in referenced_location_ids:
                    continue
                name = _provider_label(record, "Name", "LocationName")
                if not name:
                    conflict("location_missing_name", provider_id, "Referenced Metrc location has no operator label; no local room was invented.")
                    continue
                linked = existing_provider_link("locations", provider_id, "cultivation_room")
                if linked is False:
                    continue
                if linked is not None:
                    room = rooms_by_id.get(linked.entity_id)
                    if room is None:
                        conflict("orphan_location_link", provider_id, "Metrc location link points to a missing cultivation room.")
                        continue
                    add_link(entity_type="cultivation_room", entity_id=room.id, resource="locations", provider_id=provider_id, label=name)
                    location_by_provider_id[provider_id] = room
                    continue

                room_code = _safe_code(name, prefix="METRC-LOC", provider_id=provider_id)
                collision = rooms_by_code.get(room_code.casefold())
                if collision is not None:
                    conflict(
                        "location_name_collision",
                        provider_id,
                        "A local cultivation room already uses this Metrc location label but has no exact provider identity; it was not rebound by name.",
                    )
                    continue
                room = CultivationRoom(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    room_code=room_code,
                    display_name=name,
                    phase="",
                    plant_capacity=0,
                    square_feet=0.0,
                    target_cycle_days=0,
                    active=True,
                    notes="",
                )
                session.add(room)
                session.flush()
                rooms_by_id[room.id] = room
                rooms_by_code[room.room_code.casefold()] = room
                counters["created_rooms"] += 1
                if add_link(entity_type="cultivation_room", entity_id=room.id, resource="locations", provider_id=provider_id, label=name):
                    location_by_provider_id[provider_id] = room

            group_by_provider_id: dict[str, CultivationPlantGroup] = {}
            for record in plant_batches:
                if not isinstance(record, dict):
                    continue
                provider_id = _provider_id(record)
                name = _provider_label(record, "Name")
                strain = _strain(record)
                if not provider_id or not name or not strain:
                    conflict(
                        "plant_batch_missing_identity",
                        provider_id,
                        "Metrc plant batch requires exact provider id, label, and strain before a canonical group can be seeded.",
                    )
                    continue
                linked = existing_provider_link("plant_batches", provider_id, "cultivation_group")
                location_id, location_name = _location_ref(record)
                linked_room = location_by_provider_id.get(location_id)
                room_code = linked_room.room_code if linked_room is not None else (location_name or "UNASSIGNED")
                if linked is False:
                    continue
                if linked is not None:
                    group = groups_by_id.get(linked.entity_id)
                    if group is None:
                        conflict("orphan_plant_batch_link", provider_id, "Metrc plant-batch link points to a missing cultivation group.")
                        continue
                    add_link(entity_type="cultivation_group", entity_id=group.id, resource="plant_batches", provider_id=provider_id, label=name)
                    group_by_provider_id[provider_id] = group
                    if group.strain_name != strain or group.room_code != room_code:
                        warning("existing_group_metadata_differs", provider_id, "Linked local cultivation group differs from current Metrc strain/location; local operational values were preserved.")
                    continue

                group_code = _safe_code(name, prefix="METRC-BATCH", provider_id=provider_id)
                if groups_by_code.get(group_code.casefold()) is not None:
                    conflict(
                        "plant_batch_code_collision",
                        provider_id,
                        "A local cultivation group already uses this Metrc batch label without an exact provider identity; hydration did not guess a match.",
                    )
                    continue
                group = CultivationPlantGroup(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    group_code=group_code,
                    group_type=_group_type(record),
                    strain_name=strain,
                    room_code=room_code,
                    status="active",
                    created_by=actor,
                    notes="",
                )
                session.add(group)
                session.flush()
                groups_by_id[group.id] = group
                groups_by_code[group.group_code.casefold()] = group
                counters["created_groups"] += 1
                if add_link(entity_type="cultivation_group", entity_id=group.id, resource="plant_batches", provider_id=provider_id, label=name):
                    group_by_provider_id[provider_id] = group

            existing_memberships = {
                (row.group_id, row.plant_id)
                for row in session.scalars(select(CultivationPlantGroupMember).where(
                    CultivationPlantGroupMember.organization_id == organization_id,
                    CultivationPlantGroupMember.facility_id == facility_id,
                ))
            }

            def seed_plants(records: list[dict[str, Any]], phase: str) -> None:
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    provider_id = _provider_id(record)
                    tag = _provider_label(record, "Label", "Tag")
                    strain = _strain(record)
                    if not provider_id or not tag or not strain:
                        conflict(
                            "plant_missing_identity",
                            provider_id,
                            "Metrc plant requires exact provider id, regulatory tag, and strain before canonical hydration.",
                        )
                        continue
                    linked = existing_provider_link("plants", provider_id, "cultivation_plant")
                    location_id, location_name = _location_ref(record)
                    linked_room = location_by_provider_id.get(location_id)
                    room_code = linked_room.room_code if linked_room is not None else (location_name or "UNASSIGNED")
                    source = _source(record)
                    planted_at = _parse_date(_first(source, "PlantedDate", "plantedDate", "PlantDate", "plantDate"))
                    plant: CultivationPlant | None = None
                    if linked is False:
                        continue
                    if linked is not None:
                        plant = plants_by_id.get(linked.entity_id)
                        if plant is None:
                            conflict("orphan_plant_link", provider_id, "Metrc plant link points to a missing cultivation plant.")
                            continue
                        add_link(entity_type="cultivation_plant", entity_id=plant.id, resource="plants", provider_id=provider_id, label=tag)
                    else:
                        plant = plants_by_tag.get(tag.casefold())
                        if plant is not None:
                            if not add_link(entity_type="cultivation_plant", entity_id=plant.id, resource="plants", provider_id=provider_id, label=tag):
                                continue
                            warning("existing_plant_tag_linked", provider_id, "Existing local plant carried the exact Metrc regulatory tag; identity was linked without overwriting local phase, strain, or room.")
                        else:
                            plant = CultivationPlant(
                                organization_id=organization_id,
                                facility_id=facility_id,
                                plant_tag=tag,
                                strain_name=strain,
                                phase=phase,
                                room_code=room_code,
                                planted_at=planted_at,
                                notes="",
                            )
                            session.add(plant)
                            session.flush()
                            plants_by_id[plant.id] = plant
                            plants_by_tag[tag.casefold()] = plant
                            counters["created_plants"] += 1
                            if not add_link(entity_type="cultivation_plant", entity_id=plant.id, resource="plants", provider_id=provider_id, label=tag):
                                continue
                    if plant.phase != phase or plant.strain_name != strain or plant.room_code != room_code:
                        warning("existing_plant_metadata_differs", provider_id, "Linked local plant differs from current Metrc phase/strain/location; reconciliation owns the difference and local state was preserved.")

                    batch_id = _plant_batch_id(record)
                    group = group_by_provider_id.get(batch_id)
                    if group is not None and (group.id, plant.id) not in existing_memberships:
                        session.add(CultivationPlantGroupMember(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            group_id=group.id,
                            plant_id=plant.id,
                            added_by=actor,
                        ))
                        existing_memberships.add((group.id, plant.id))
                        counters["created_group_memberships"] += 1

            seed_plants(vegetative_plants, "vegetative")
            seed_plants(flowering_plants, "flowering")

            for record in harvests:
                if not isinstance(record, dict):
                    continue
                provider_id = _provider_id(record)
                name = _provider_label(record, "Name")
                strain = _harvest_strain(record)
                if not provider_id or not name or not strain:
                    conflict(
                        "harvest_missing_identity",
                        provider_id,
                        "Metrc harvest requires exact provider id, label, and source strain before a canonical harvest can be seeded.",
                    )
                    continue
                linked = existing_provider_link("harvests", provider_id, "cultivation_harvest")
                location_id, location_name = _location_ref(record)
                linked_room = location_by_provider_id.get(location_id)
                room_code = linked_room.room_code if linked_room is not None else location_name
                source = _source(record)
                harvested_at = _parse_datetime(_first(source, "HarvestStartDate", "harvestStartDate", "StartDate", "startDate", "ActualDate"))
                plant_count = _integer(_first(source, "CurrentPlantCount", "PlantCount", "plantCount"))
                if linked is False:
                    continue
                if linked is not None:
                    harvest = harvests_by_id.get(linked.entity_id)
                    if harvest is None:
                        conflict("orphan_harvest_link", provider_id, "Metrc harvest link points to a missing local harvest.")
                        continue
                    add_link(entity_type="cultivation_harvest", entity_id=harvest.id, resource="harvests", provider_id=provider_id, label=name)
                    if harvest.strain != strain or (room_code and harvest.room != room_code):
                        warning("existing_harvest_metadata_differs", provider_id, "Linked local harvest differs from current Metrc strain/location; local lifecycle state was preserved.")
                    continue

                harvest_code = _safe_code(name, prefix="METRC-HARVEST", provider_id=provider_id)
                if harvests_by_code.get(harvest_code.casefold()) is not None:
                    conflict(
                        "harvest_code_collision",
                        provider_id,
                        "A local harvest already uses this Metrc label without an exact provider identity; hydration did not guess a match.",
                    )
                    continue
                harvest = CultivationHarvest(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    harvest_code=harvest_code,
                    strain=strain,
                    room=room_code,
                    plant_count=plant_count,
                    wet_weight_g=0.0,
                    dry_weight_g=0.0,
                    waste_weight_g=0.0,
                    labor_hours=0.0,
                    status="active",
                    harvested_at=harvested_at,
                    notes="",
                    created_by=actor,
                )
                session.add(harvest)
                session.flush()
                harvests_by_id[harvest.id] = harvest
                harvests_by_code[harvest.harvest_code.casefold()] = harvest
                counters["created_harvests"] += 1
                add_link(entity_type="cultivation_harvest", entity_id=harvest.id, resource="harvests", provider_id=provider_id, label=name)

            summary = {
                "workspace": "cultivation",
                "mode": "materialized",
                "source_counts": {
                    "locations": len(locations),
                    "plant_batches": len(plant_batches),
                    "vegetative_plants": len(vegetative_plants),
                    "flowering_plants": len(flowering_plants),
                    "harvests": len(harvests),
                },
                **counters,
                "conflict_count": len(conflicts),
                "warning_count": len(warnings),
                "conflicts": conflicts[:200],
                "warnings": warnings[:200],
                "overwrite_existing": False,
                "fabricated_lifecycle_history": False,
            }
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="metrc_workspace_hydration",
                entity_id=facility_id,
                action="metrc_cultivation_hydration_completed",
                actor=actor,
                changes_json=json.dumps(
                    {key: value for key, value in summary.items() if key not in {"conflicts", "warnings"}},
                    sort_keys=True,
                    default=str,
                ),
            ))
            return summary
