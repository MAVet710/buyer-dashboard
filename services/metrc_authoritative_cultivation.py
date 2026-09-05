from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Mapping

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, utc_now
from modules.cultivation.batch_models import CultivationPlantGroup
from modules.cultivation.models import CultivationPlant, CultivationPlantEvent, CultivationRoom
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


def _provider_label(record: Mapping[str, Any], *keys: str) -> str:
    source = _source(record)
    return _text(record.get("label") or record.get("name") or _first(source, *keys, "Label", "Name"))


def _explicit_strain(record: Mapping[str, Any], *, harvest: bool = False) -> str:
    source = _source(record)
    keys = (
        ("SourceStrainNames", "sourceStrainNames", "StrainName", "strainName", "Strain", "strain")
        if harvest
        else ("StrainName", "strainName", "Strain", "strain")
    )
    return _nested_name(_first(source, *keys))


def _location_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    nested = _first(source, "Location", "location", "DryingLocation", "dryingLocation")
    nested_id = ""
    if isinstance(nested, Mapping):
        nested_id = _text(nested.get("Id") or nested.get("id"))
    return _text(
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


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def _group_type(record: Mapping[str, Any]) -> str | None:
    source = _source(record)
    raw = _text(
        _first(source, "Type", "type", "PlantBatchType", "plantBatchType", "PlantBatchTypeName", "TypeName")
    ).casefold()
    if not raw:
        return None
    if "seed" in raw:
        return "seed_batch"
    if "clone" in raw:
        return "clone_batch"
    if "veget" in raw:
        return "vegetative"
    if "flower" in raw:
        return "flowering"
    return "nursery"


class MetrcAuthoritativeCultivationReconciler:
    """Project verified Metrc cultivation state into canonical DoobieLogic objects.

    Metrc is authoritative for regulated identity and the explicit lifecycle fields
    it reports. Exact provider links are required; mutable names never establish
    identity. Entity rows are batch-loaded for realistic facility scale, and every
    regulated correction receives durable per-object audit evidence.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def reconcile(
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
            raise ValueError("Cultivation reconciliation requires exact jurisdiction, environment, and license scope.")

        counters = {
            "room_updates": 0,
            "group_updates": 0,
            "plant_updates": 0,
            "harvest_updates": 0,
            "plant_events": 0,
            "unchanged": 0,
            "skipped": 0,
        }
        conflicts: list[dict[str, str]] = []
        reconciled: list[dict[str, Any]] = []

        def conflict(code: str, provider_id: str, message: str) -> None:
            conflicts.append({"code": code, "provider_id": provider_id, "message": message})

        with self.sessions.begin() as session:
            links = list(
                session.scalars(
                    select(TraceabilityObjectLink).where(
                        TraceabilityObjectLink.organization_id == organization_id,
                        TraceabilityObjectLink.facility_id == facility_id,
                        TraceabilityObjectLink.provider == "metrc",
                        TraceabilityObjectLink.environment == environment,
                    )
                )
            )
            provider_links = {(row.provider_resource, row.provider_id): row for row in links}

            def scoped_entity_ids(entity_type: str) -> set[str]:
                return {
                    row.entity_id
                    for row in links
                    if row.entity_type == entity_type
                    and row.license_number == license_number
                    and row.jurisdiction == state
                }

            room_ids = scoped_entity_ids("cultivation_room")
            group_ids = scoped_entity_ids("cultivation_group")
            plant_ids = scoped_entity_ids("cultivation_plant")
            harvest_ids = scoped_entity_ids("cultivation_harvest")

            rooms = {
                row.id: row
                for row in session.scalars(
                    select(CultivationRoom).where(
                        CultivationRoom.id.in_(room_ids),
                        CultivationRoom.organization_id == organization_id,
                        CultivationRoom.facility_id == facility_id,
                    )
                )
            } if room_ids else {}
            groups = {
                row.id: row
                for row in session.scalars(
                    select(CultivationPlantGroup).where(
                        CultivationPlantGroup.id.in_(group_ids),
                        CultivationPlantGroup.organization_id == organization_id,
                        CultivationPlantGroup.facility_id == facility_id,
                    )
                )
            } if group_ids else {}
            plants = {
                row.id: row
                for row in session.scalars(
                    select(CultivationPlant).where(
                        CultivationPlant.id.in_(plant_ids),
                        CultivationPlant.organization_id == organization_id,
                        CultivationPlant.facility_id == facility_id,
                    )
                )
            } if plant_ids else {}
            local_harvests = {
                row.id: row
                for row in session.scalars(
                    select(CultivationHarvest).where(
                        CultivationHarvest.id.in_(harvest_ids),
                        CultivationHarvest.organization_id == organization_id,
                        CultivationHarvest.facility_id == facility_id,
                    )
                )
            } if harvest_ids else {}

            def exact_link(resource: str, provider_id: str, entity_type: str) -> TraceabilityObjectLink | None:
                link = provider_links.get((resource, provider_id))
                if link is None:
                    conflict(
                        f"unlinked_{resource}",
                        provider_id,
                        "No exact Metrc identity link exists; DoobieLogic did not reconcile by a mutable name or label.",
                    )
                    counters["skipped"] += 1
                    return None
                if link.license_number != license_number or link.jurisdiction != state or link.entity_type != entity_type:
                    link.status = "reconciliation_required"
                    link.mismatch_reason = "Metrc identity scope or local object type does not match this facility/license."
                    conflict("identity_scope_mismatch", provider_id, link.mismatch_reason)
                    counters["skipped"] += 1
                    return None
                return link

            def exact_room(provider_location_id: str) -> CultivationRoom | None:
                if not provider_location_id:
                    return None
                link = provider_links.get(("locations", provider_location_id))
                if (
                    link is None
                    or link.license_number != license_number
                    or link.jurisdiction != state
                    or link.entity_type != "cultivation_room"
                ):
                    return None
                room = rooms.get(link.entity_id)
                if room is None:
                    link.status = "reconciliation_required"
                    link.mismatch_reason = "Metrc location identity points to a missing or out-of-scope cultivation room."
                    return None
                return room

            def verify_link(link: TraceabilityObjectLink, *, label: str = "") -> None:
                now = utc_now()
                link.status = "verified"
                link.mismatch_reason = ""
                link.provider_label = label or link.provider_label
                link.verified_at = now
                link.last_seen_at = now

            def record_reconciliation(
                *,
                resource: str,
                provider_id: str,
                entity_type: str,
                entity_id: str,
                changes: dict[str, Any],
            ) -> None:
                evidence = {
                    "provider": "metrc",
                    "resource": resource,
                    "provider_id": provider_id,
                    "environment": environment,
                    "jurisdiction_code": state,
                    "license_number": license_number,
                    "changes": changes,
                }
                reconciled.append({"resource": resource, "provider_id": provider_id, "entity_id": entity_id, "changes": changes})
                session.add(
                    AuditEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        action=f"metrc_{resource}_authoritative_reconciliation",
                        actor=actor,
                        changes_json=json.dumps(evidence, sort_keys=True, default=str),
                    )
                )

            referenced_location_ids = {
                location_id
                for record in [*plant_batches, *vegetative_plants, *flowering_plants, *harvests]
                if isinstance(record, dict)
                for location_id in [_location_id(record)]
                if location_id
            }

            for record in locations:
                if not isinstance(record, dict):
                    continue
                provider_id = _provider_id(record)
                if not provider_id or provider_id not in referenced_location_ids:
                    continue
                link = exact_link("locations", provider_id, "cultivation_room")
                if link is None:
                    continue
                room = rooms.get(link.entity_id)
                if room is None:
                    link.status = "reconciliation_required"
                    link.mismatch_reason = "Exact Metrc location link points to a missing or out-of-scope room."
                    conflict("orphan_location_link", provider_id, link.mismatch_reason)
                    counters["skipped"] += 1
                    continue
                name = _provider_label(record, "Name", "LocationName")
                changes: dict[str, Any] = {}
                if name and room.display_name != name:
                    changes["display_name"] = {"before": room.display_name, "after": name}
                    room.display_name = name
                if not room.active:
                    changes["active"] = {"before": False, "after": True}
                    room.active = True
                verify_link(link, label=name)
                if changes:
                    counters["room_updates"] += 1
                    record_reconciliation(
                        resource="locations",
                        provider_id=provider_id,
                        entity_type="cultivation_room",
                        entity_id=room.id,
                        changes=changes,
                    )
                else:
                    counters["unchanged"] += 1

            for record in plant_batches:
                if not isinstance(record, dict):
                    continue
                provider_id = _provider_id(record)
                if not provider_id:
                    continue
                link = exact_link("plant_batches", provider_id, "cultivation_group")
                if link is None:
                    continue
                group = groups.get(link.entity_id)
                if group is None:
                    link.status = "reconciliation_required"
                    link.mismatch_reason = "Exact Metrc plant-batch link points to a missing or out-of-scope cultivation group."
                    conflict("orphan_plant_batch_link", provider_id, link.mismatch_reason)
                    counters["skipped"] += 1
                    continue
                changes: dict[str, Any] = {}
                strain = _explicit_strain(record)
                if strain and group.strain_name != strain:
                    changes["strain_name"] = {"before": group.strain_name, "after": strain}
                    group.strain_name = strain
                provider_group_type = _group_type(record)
                if provider_group_type and group.group_type != provider_group_type:
                    changes["group_type"] = {"before": group.group_type, "after": provider_group_type}
                    group.group_type = provider_group_type
                provider_location_id = _location_id(record)
                if provider_location_id:
                    room = exact_room(provider_location_id)
                    if room is None:
                        conflict(
                            "plant_batch_location_unlinked",
                            provider_id,
                            "Metrc plant batch references a location without an exact local Metrc location link; room was not guessed by name.",
                        )
                    elif group.room_code != room.room_code:
                        changes["room_code"] = {"before": group.room_code, "after": room.room_code}
                        group.room_code = room.room_code
                verify_link(link, label=_provider_label(record, "Name"))
                if changes:
                    counters["group_updates"] += 1
                    record_reconciliation(
                        resource="plant_batches",
                        provider_id=provider_id,
                        entity_type="cultivation_group",
                        entity_id=group.id,
                        changes=changes,
                    )
                else:
                    counters["unchanged"] += 1

            def reconcile_plants(records: list[dict[str, Any]], phase: str) -> None:
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    provider_id = _provider_id(record)
                    if not provider_id:
                        continue
                    link = exact_link("plants", provider_id, "cultivation_plant")
                    if link is None:
                        continue
                    plant = plants.get(link.entity_id)
                    if plant is None:
                        link.status = "reconciliation_required"
                        link.mismatch_reason = "Exact Metrc plant link points to a missing or out-of-scope cultivation plant."
                        conflict("orphan_plant_link", provider_id, link.mismatch_reason)
                        counters["skipped"] += 1
                        continue
                    tag = _provider_label(record, "Label", "Tag")
                    if tag and plant.plant_tag != tag:
                        link.status = "reconciliation_required"
                        link.mismatch_reason = "Metrc regulatory plant tag differs from the exact linked local plant tag."
                        conflict("plant_tag_mismatch", provider_id, link.mismatch_reason)
                        counters["skipped"] += 1
                        continue

                    changes: dict[str, Any] = {}
                    if plant.phase != phase:
                        before = plant.phase
                        plant.phase = phase
                        changes["phase"] = {"before": before, "after": phase}
                        session.add(
                            CultivationPlantEvent(
                                organization_id=organization_id,
                                facility_id=facility_id,
                                plant_id=plant.id,
                                event_type="metrc_phase_reconciled",
                                from_value=before,
                                to_value=phase,
                                reason="Metrc authoritative lifecycle state",
                                notes="",
                                actor=actor,
                            )
                        )
                        counters["plant_events"] += 1

                    strain = _explicit_strain(record)
                    if strain and plant.strain_name != strain:
                        before = plant.strain_name
                        plant.strain_name = strain
                        changes["strain_name"] = {"before": before, "after": strain}
                        session.add(
                            CultivationPlantEvent(
                                organization_id=organization_id,
                                facility_id=facility_id,
                                plant_id=plant.id,
                                event_type="metrc_strain_reconciled",
                                from_value=before,
                                to_value=strain,
                                reason="Metrc authoritative strain identity",
                                notes="",
                                actor=actor,
                            )
                        )
                        counters["plant_events"] += 1

                    provider_location_id = _location_id(record)
                    if provider_location_id:
                        room = exact_room(provider_location_id)
                        if room is None:
                            conflict(
                                "plant_location_unlinked",
                                provider_id,
                                "Metrc plant references a location without an exact local Metrc location link; room was not guessed by name.",
                            )
                        elif plant.room_code != room.room_code:
                            before = plant.room_code
                            plant.room_code = room.room_code
                            changes["room_code"] = {"before": before, "after": room.room_code}
                            session.add(
                                CultivationPlantEvent(
                                    organization_id=organization_id,
                                    facility_id=facility_id,
                                    plant_id=plant.id,
                                    event_type="metrc_location_reconciled",
                                    from_value=before,
                                    to_value=room.room_code,
                                    reason="Metrc authoritative plant location",
                                    notes="",
                                    actor=actor,
                                )
                            )
                            counters["plant_events"] += 1

                    source = _source(record)
                    provider_planted_at = _parse_date(
                        _first(source, "PlantedDate", "plantedDate", "PlantDate", "plantDate")
                    )
                    if provider_planted_at is not None and plant.planted_at != provider_planted_at:
                        changes["planted_at"] = {
                            "before": plant.planted_at.isoformat() if plant.planted_at else None,
                            "after": provider_planted_at.isoformat(),
                        }
                        plant.planted_at = provider_planted_at

                    verify_link(link, label=tag)
                    if changes:
                        counters["plant_updates"] += 1
                        record_reconciliation(
                            resource="plants",
                            provider_id=provider_id,
                            entity_type="cultivation_plant",
                            entity_id=plant.id,
                            changes=changes,
                        )
                    else:
                        counters["unchanged"] += 1

            reconcile_plants(vegetative_plants, "vegetative")
            reconcile_plants(flowering_plants, "flowering")

            for record in harvests:
                if not isinstance(record, dict):
                    continue
                provider_id = _provider_id(record)
                if not provider_id:
                    continue
                link = exact_link("harvests", provider_id, "cultivation_harvest")
                if link is None:
                    continue
                harvest = local_harvests.get(link.entity_id)
                if harvest is None:
                    link.status = "reconciliation_required"
                    link.mismatch_reason = "Exact Metrc harvest link points to a missing or out-of-scope local harvest."
                    conflict("orphan_harvest_link", provider_id, link.mismatch_reason)
                    counters["skipped"] += 1
                    continue
                changes: dict[str, Any] = {}
                strain = _explicit_strain(record, harvest=True)
                if strain and harvest.strain != strain:
                    changes["strain"] = {"before": harvest.strain, "after": strain}
                    harvest.strain = strain
                provider_location_id = _location_id(record)
                if provider_location_id:
                    room = exact_room(provider_location_id)
                    if room is None:
                        conflict(
                            "harvest_location_unlinked",
                            provider_id,
                            "Metrc harvest references a location without an exact local Metrc location link; room was not guessed by name.",
                        )
                    elif harvest.room != room.room_code:
                        changes["room"] = {"before": harvest.room, "after": room.room_code}
                        harvest.room = room.room_code
                source = _source(record)
                plant_count = _integer(_first(source, "CurrentPlantCount", "PlantCount", "plantCount"))
                if plant_count is not None and harvest.plant_count != plant_count:
                    changes["plant_count"] = {"before": harvest.plant_count, "after": plant_count}
                    harvest.plant_count = plant_count
                harvested_at = _parse_datetime(
                    _first(source, "HarvestStartDate", "harvestStartDate", "StartDate", "startDate", "ActualDate")
                )
                if harvested_at is not None and harvest.harvested_at != harvested_at:
                    changes["harvested_at"] = {
                        "before": harvest.harvested_at.isoformat() if harvest.harvested_at else None,
                        "after": harvested_at.isoformat(),
                    }
                    harvest.harvested_at = harvested_at
                verify_link(link, label=_provider_label(record, "Name"))
                if changes:
                    counters["harvest_updates"] += 1
                    record_reconciliation(
                        resource="harvests",
                        provider_id=provider_id,
                        entity_type="cultivation_harvest",
                        entity_id=harvest.id,
                        changes=changes,
                    )
                else:
                    counters["unchanged"] += 1

            summary = {
                "provider": "metrc",
                "authoritative_provider": "metrc",
                "workspace": "cultivation",
                "environment": environment,
                "jurisdiction_code": state,
                "license_number": license_number,
                "source_counts": {
                    "locations": len(locations),
                    "plant_batches": len(plant_batches),
                    "vegetative_plants": len(vegetative_plants),
                    "flowering_plants": len(flowering_plants),
                    "harvests": len(harvests),
                },
                **counters,
                "conflict_count": len(conflicts),
                "conflicts": conflicts[:200],
                "reconciled": reconciled[:200],
                "regulated_fields": {
                    "rooms": ["display_name", "active_when_present_in_active_snapshot"],
                    "plant_batches": ["strain", "type", "location"],
                    "plants": ["tag_identity", "phase", "strain", "location", "planted_at"],
                    "harvests": ["strain", "location", "plant_count", "harvest_start"],
                },
                "local_enrichment_preserved": [
                    "room capacity/square footage/cycle targets/notes",
                    "plant notes/estimated harvest date/source lot/mother metadata",
                    "harvest wet/dry/waste weights/labor/notes",
                ],
                "terminal_state_inferred_from_absence": False,
                "harvest_weight_reconciliation_enabled": False,
                "identity_strategy": "exact_traceability_object_link",
                "entity_loading_strategy": "batched_by_linked_entity_type",
                "unused_provider_locations_ignored": True,
                "per_object_audit_evidence": True,
            }
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="metrc_authoritative_cultivation",
                    entity_id=facility_id,
                    action="metrc_authoritative_cultivation_reconciliation_completed",
                    actor=actor,
                    changes_json=json.dumps(
                        {key: value for key, value in summary.items() if key != "conflicts"},
                        sort_keys=True,
                        default=str,
                    ),
                )
            )
            return summary
