from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, Organization
from modules.cultivation.batch_models import CultivationPlantGroup
from modules.cultivation.models import CultivationPlant, CultivationPlantEvent, CultivationRoom
from modules.operational_moats.models import CultivationHarvest
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_authoritative_cultivation import MetrcAuthoritativeCultivationReconciler
from services.metrc_expanded_workspace_hydration import MetrcWorkspaceHydrationService


def _facility():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Metrc Authority", slug="metrc-authority", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Authority Cultivation",
            code="MC-AUTH",
            license_number="MC-AUTH",
            cultivation_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return engine, organization.id, facility.id


def _location(provider_id: str, name: str) -> dict:
    return {
        "provider_id": provider_id,
        "name": name,
        "source": {"Id": provider_id, "Name": name},
    }


def _batch(*, location_id: str = "loc-1", location_name: str = "VEG 1", strain: str = "GMO", kind: str = "Clone") -> dict:
    return {
        "provider_id": "batch-1",
        "name": "GMO BATCH 1",
        "source": {
            "Id": "batch-1",
            "Name": "GMO BATCH 1",
            "StrainName": strain,
            "Type": kind,
            "LocationId": location_id,
            "LocationName": location_name,
        },
    }


def _plant(*, provider_id: str = "plant-1", tag: str = "1A4FF0100000000000001001", location_id: str = "loc-1", location_name: str = "VEG 1", strain: str = "GMO", batch_id: str = "batch-1") -> dict:
    return {
        "provider_id": provider_id,
        "label": tag,
        "name": strain,
        "source": {
            "Id": provider_id,
            "Label": tag,
            "StrainName": strain,
            "LocationId": location_id,
            "LocationName": location_name,
            "PlantBatchId": batch_id,
            "PlantedDate": "2026-08-01T00:00:00Z",
        },
    }


def _harvest(*, location_id: str = "loc-1", location_name: str = "VEG 1", strain: str = "GMO", plant_count: int = 1, started: str = "2026-09-01T10:00:00Z") -> dict:
    return {
        "provider_id": "harvest-1",
        "name": "GMO H1",
        "source": {
            "Id": "harvest-1",
            "Name": "GMO H1",
            "SourceStrainNames": [strain],
            "DryingLocationId": location_id,
            "DryingLocationName": location_name,
            "HarvestStartDate": started,
            "CurrentPlantCount": plant_count,
        },
    }


def _snapshots() -> dict[str, list[dict]]:
    return {
        "locations": [_location("loc-1", "VEG 1"), _location("loc-2", "FLOWER 1")],
        "plant_batches": [_batch()],
        "plants_vegetative": [_plant()],
        "plants_flowering": [
            _plant(
                provider_id="plant-2",
                tag="1A4FF0100000000000001002",
                location_id="loc-2",
                location_name="FLOWER 1",
                batch_id="",
            )
        ],
        "harvests": [_harvest()],
    }


def _hydrate(engine, organization_id: str, facility_id: str, snapshots: dict[str, list[dict]]):
    return MetrcWorkspaceHydrationService(engine).hydrate(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="MC-AUTH",
        actor="admin",
        resource_snapshots=snapshots,
    )


def test_linked_plant_phase_strain_and_location_follow_metrc_with_events_and_local_enrichment_preserved():
    engine, organization_id, facility_id = _facility()
    snapshots = _snapshots()
    first = _hydrate(engine, organization_id, facility_id, snapshots)
    assert first["workspaces"]["cultivation"]["authority"] == "metrc"

    with Session(engine) as session, session.begin():
        plant = session.scalar(select(CultivationPlant).where(CultivationPlant.plant_tag == "1A4FF0100000000000001001"))
        assert plant is not None
        plant.phase = "flowering"
        plant.strain_name = "LOCAL STRAIN"
        plant.room_code = "LOCAL ROOM"
        plant.estimated_harvest_date = date(2026, 10, 20)
        plant.notes = "Keep this operator note"
        plant_id = plant.id

    result = _hydrate(engine, organization_id, facility_id, snapshots)
    authority = result["workspaces"]["cultivation"]["authoritative_reconciliation"]
    assert authority["plant_updates"] >= 1
    assert authority["plant_events"] >= 3
    assert authority["terminal_state_inferred_from_absence"] is False
    assert authority["harvest_weight_reconciliation_enabled"] is False

    with Session(engine) as session:
        plant = session.get(CultivationPlant, plant_id)
        assert plant is not None
        assert plant.phase == "vegetative"
        assert plant.strain_name == "GMO"
        assert plant.room_code == "VEG 1"
        assert plant.estimated_harvest_date == date(2026, 10, 20)
        assert plant.notes == "Keep this operator note"
        events = list(session.scalars(select(CultivationPlantEvent).where(CultivationPlantEvent.plant_id == plant_id)))
        assert {row.event_type for row in events} >= {
            "metrc_phase_reconciled",
            "metrc_strain_reconciled",
            "metrc_location_reconciled",
        }

    replay = _hydrate(engine, organization_id, facility_id, snapshots)
    assert replay["workspaces"]["cultivation"]["authoritative_reconciliation"]["plant_updates"] == 0
    with Session(engine) as session:
        assert len(list(session.scalars(select(CultivationPlantEvent).where(CultivationPlantEvent.plant_id == plant_id)))) == len(events)


def test_exact_metrc_plant_tag_mismatch_fails_closed_and_marks_identity_for_reconciliation():
    engine, organization_id, facility_id = _facility()
    snapshots = _snapshots()
    _hydrate(engine, organization_id, facility_id, snapshots)

    with Session(engine) as session, session.begin():
        plant = session.scalar(select(CultivationPlant).where(CultivationPlant.plant_tag == "1A4FF0100000000000001001"))
        assert plant is not None
        plant.plant_tag = "LOCAL-DIVERGED-TAG"
        plant.phase = "flowering"
        plant_id = plant.id

    result = _hydrate(engine, organization_id, facility_id, snapshots)
    authority = result["workspaces"]["cultivation"]["authoritative_reconciliation"]
    assert any(row["code"] == "plant_tag_mismatch" for row in authority["conflicts"])

    with Session(engine) as session:
        plant = session.get(CultivationPlant, plant_id)
        assert plant is not None
        assert plant.plant_tag == "LOCAL-DIVERGED-TAG"
        assert plant.phase == "flowering"
        link = session.scalar(select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.provider_resource == "plants",
            TraceabilityObjectLink.provider_id == "plant-1",
        ))
        assert link is not None
        assert link.status == "reconciliation_required"
        assert "tag differs" in link.mismatch_reason.lower()


def test_plant_location_is_never_rebound_by_name_without_exact_metrc_location_identity():
    engine, organization_id, facility_id = _facility()
    snapshots = _snapshots()
    _hydrate(engine, organization_id, facility_id, snapshots)

    with Session(engine) as session, session.begin():
        plant = session.scalar(select(CultivationPlant).where(CultivationPlant.plant_tag == "1A4FF0100000000000001001"))
        assert plant is not None
        plant.room_code = "LOCAL ROOM"
        plant_id = plant.id

    changed = _snapshots()
    changed["plants_vegetative"] = [
        _plant(location_id="loc-unlinked", location_name="VEG 1")
    ]
    changed["locations"] = [_location("loc-1", "VEG 1"), _location("loc-2", "FLOWER 1")]

    result = _hydrate(engine, organization_id, facility_id, changed)
    authority = result["workspaces"]["cultivation"]["authoritative_reconciliation"]
    assert any(row["code"] == "plant_location_unlinked" for row in authority["conflicts"])
    with Session(engine) as session:
        plant = session.get(CultivationPlant, plant_id)
        assert plant is not None
        assert plant.room_code == "LOCAL ROOM"


def test_group_and_harvest_regulated_metadata_follow_metrc_while_post_harvest_enrichment_is_preserved():
    engine, organization_id, facility_id = _facility()
    snapshots = _snapshots()
    _hydrate(engine, organization_id, facility_id, snapshots)

    with Session(engine) as session, session.begin():
        group = session.scalar(select(CultivationPlantGroup).where(CultivationPlantGroup.group_code == "GMO BATCH 1"))
        harvest = session.scalar(select(CultivationHarvest).where(CultivationHarvest.harvest_code == "GMO H1"))
        assert group is not None and harvest is not None
        group.strain_name = "LOCAL BATCH STRAIN"
        group.group_type = "nursery"
        group.room_code = "LOCAL GROUP ROOM"
        group.notes = "Local batch planning note"
        harvest.strain = "LOCAL HARVEST STRAIN"
        harvest.room = "LOCAL HARVEST ROOM"
        harvest.plant_count = 99
        harvest.wet_weight_g = 1250.0
        harvest.dry_weight_g = 310.0
        harvest.waste_weight_g = 80.0
        harvest.labor_hours = 12.5
        harvest.notes = "Local post-harvest note"
        group_id = group.id
        harvest_id = harvest.id

    changed = _snapshots()
    changed["plant_batches"] = [
        _batch(location_id="loc-2", location_name="FLOWER 1", strain="GMO V2", kind="Seed")
    ]
    changed["harvests"] = [
        _harvest(
            location_id="loc-2",
            location_name="FLOWER 1",
            strain="GMO V2",
            plant_count=7,
            started="2026-09-03T12:30:00Z",
        )
    ]

    result = _hydrate(engine, organization_id, facility_id, changed)
    authority = result["workspaces"]["cultivation"]["authoritative_reconciliation"]
    assert authority["group_updates"] == 1
    assert authority["harvest_updates"] == 1

    with Session(engine) as session:
        group = session.get(CultivationPlantGroup, group_id)
        harvest = session.get(CultivationHarvest, harvest_id)
        assert group is not None and harvest is not None
        assert group.strain_name == "GMO V2"
        assert group.group_type == "seed_batch"
        assert group.room_code == "FLOWER 1"
        assert group.notes == "Local batch planning note"
        assert harvest.strain == "GMO V2"
        assert harvest.room == "FLOWER 1"
        assert harvest.plant_count == 7
        assert harvest.harvested_at is not None and harvest.harvested_at.date() == date(2026, 9, 3)
        assert harvest.wet_weight_g == 1250.0
        assert harvest.dry_weight_g == 310.0
        assert harvest.waste_weight_g == 80.0
        assert harvest.labor_hours == 12.5
        assert harvest.notes == "Local post-harvest note"


def test_absence_from_active_cultivation_collections_never_infers_terminal_state():
    engine, organization_id, facility_id = _facility()
    snapshots = _snapshots()
    _hydrate(engine, organization_id, facility_id, snapshots)

    with Session(engine) as session:
        plant = session.scalar(select(CultivationPlant).where(CultivationPlant.plant_tag == "1A4FF0100000000000001001"))
        assert plant is not None
        plant_id = plant.id
        before_phase = plant.phase
        before_retired = plant.retired_at

    result = MetrcAuthoritativeCultivationReconciler(engine).reconcile(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="MC-AUTH",
        actor="admin",
        locations=[],
        plant_batches=[],
        vegetative_plants=[],
        flowering_plants=[],
        harvests=[],
    )
    assert result["terminal_state_inferred_from_absence"] is False
    with Session(engine) as session:
        plant = session.get(CultivationPlant, plant_id)
        assert plant is not None
        assert plant.phase == before_phase
        assert plant.retired_at == before_retired
