from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.cultivation.batch_models import CultivationPlantGroup, CultivationPlantGroupMember
from modules.cultivation.models import CultivationPlant, CultivationPlantEvent, CultivationRoom
from modules.operational_moats.models import CultivationHarvest
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_expanded_workspace_hydration import MetrcWorkspaceHydrationService


def _facility():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Metrc Cultivation Hydration", slug="metrc-cultivation-hydration", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Cultivation License",
            code="MC281234",
            license_number="MC281234",
            cultivation_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return engine, organization.id, facility.id


def _snapshots():
    return {
        "locations": [
            {
                "provider_id": "loc-veg-1",
                "name": "VEG 1",
                "source": {"Id": "loc-veg-1", "Name": "VEG 1"},
            }
        ],
        "plant_batches": [
            {
                "provider_id": "batch-1",
                "name": "GMO CLONES 001",
                "source": {
                    "Id": "batch-1",
                    "Name": "GMO CLONES 001",
                    "StrainName": "GMO",
                    "Type": "Clone",
                    "LocationId": "loc-veg-1",
                    "LocationName": "VEG 1",
                },
            }
        ],
        "plants_vegetative": [
            {
                "provider_id": "plant-1",
                "label": "1A4FF0100000000000000001",
                "name": "GMO",
                "source": {
                    "Id": "plant-1",
                    "Label": "1A4FF0100000000000000001",
                    "StrainName": "GMO",
                    "LocationId": "loc-veg-1",
                    "LocationName": "VEG 1",
                    "PlantBatchId": "batch-1",
                    "PlantedDate": "2026-08-01T00:00:00Z",
                },
            }
        ],
        "plants_flowering": [
            {
                "provider_id": "plant-2",
                "label": "1A4FF0100000000000000002",
                "name": "GMO",
                "source": {
                    "Id": "plant-2",
                    "Label": "1A4FF0100000000000000002",
                    "StrainName": "GMO",
                    "LocationId": "loc-veg-1",
                    "LocationName": "VEG 1",
                },
            }
        ],
        "harvests": [
            {
                "provider_id": "harvest-1",
                "name": "GMO H1",
                "source": {
                    "Id": "harvest-1",
                    "Name": "GMO H1",
                    "SourceStrainNames": ["GMO"],
                    "DryingLocationId": "loc-veg-1",
                    "DryingLocationName": "VEG 1",
                    "HarvestStartDate": "2026-09-01T10:00:00Z",
                    "CurrentPlantCount": 2,
                },
            }
        ],
    }


def test_existing_metrc_cultivation_state_becomes_canonical_without_fake_history():
    engine, organization_id, facility_id = _facility()
    result = MetrcWorkspaceHydrationService(engine).hydrate(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="MC281234",
        actor="admin",
        resource_snapshots=_snapshots(),
    )

    cultivation = result["workspaces"]["cultivation"]
    assert cultivation["created_rooms"] == 1
    assert cultivation["created_groups"] == 1
    assert cultivation["created_plants"] == 2
    assert cultivation["created_harvests"] == 1
    assert cultivation["created_group_memberships"] == 1
    assert cultivation["created_links"] == 5
    assert cultivation["fabricated_lifecycle_history"] is False
    assert cultivation["authority"] == "metrc"
    assert cultivation["regulated_state_authoritative"] is True
    assert "cultivation" in result["materialized_workspaces"]

    with Session(engine) as session:
        rooms = list(session.scalars(select(CultivationRoom)))
        groups = list(session.scalars(select(CultivationPlantGroup)))
        plants = list(session.scalars(select(CultivationPlant).order_by(CultivationPlant.plant_tag)))
        harvests = list(session.scalars(select(CultivationHarvest)))
        memberships = list(session.scalars(select(CultivationPlantGroupMember)))
        events = list(session.scalars(select(CultivationPlantEvent)))
        links = list(session.scalars(select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.provider == "metrc",
            TraceabilityObjectLink.environment == "sandbox",
        )))

    assert len(rooms) == 1 and rooms[0].room_code == "VEG 1"
    assert len(groups) == 1 and groups[0].strain_name == "GMO"
    assert [(row.plant_tag, row.phase) for row in plants] == [
        ("1A4FF0100000000000000001", "vegetative"),
        ("1A4FF0100000000000000002", "flowering"),
    ]
    assert len(harvests) == 1 and harvests[0].status == "active" and harvests[0].plant_count == 2
    assert len(memberships) == 1
    assert events == []
    assert {(row.entity_type, row.provider_resource) for row in links} == {
        ("cultivation_room", "locations"),
        ("cultivation_group", "plant_batches"),
        ("cultivation_plant", "plants"),
        ("cultivation_harvest", "harvests"),
    }


def test_cultivation_hydration_replay_is_idempotent():
    engine, organization_id, facility_id = _facility()
    service = MetrcWorkspaceHydrationService(engine)
    arguments = dict(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="MC281234",
        actor="admin",
        resource_snapshots=_snapshots(),
    )
    first = service.hydrate(**arguments)["workspaces"]["cultivation"]
    second = service.hydrate(**arguments)["workspaces"]["cultivation"]
    assert first["created_plants"] == 2
    assert second["created_rooms"] == 0
    assert second["created_groups"] == 0
    assert second["created_plants"] == 0
    assert second["created_harvests"] == 0
    assert second["created_group_memberships"] == 0
    assert second["authoritative_reconciliation"]["plant_updates"] == 0

    with Session(engine) as session:
        assert len(list(session.scalars(select(CultivationRoom)))) == 1
        assert len(list(session.scalars(select(CultivationPlantGroup)))) == 1
        assert len(list(session.scalars(select(CultivationPlant)))) == 2
        assert len(list(session.scalars(select(CultivationHarvest)))) == 1
        assert len(list(session.scalars(select(CultivationPlantGroupMember)))) == 1


def test_exact_existing_plant_tag_links_then_regulated_state_reconciles_to_metrc():
    engine, organization_id, facility_id = _facility()
    with Session(engine) as session, session.begin():
        existing = CultivationPlant(
            organization_id=organization_id,
            facility_id=facility_id,
            plant_tag="1A4FF0100000000000000001",
            strain_name="LOCAL GMO",
            phase="flowering",
            room_code="LOCAL ROOM",
            notes="Keep local note",
        )
        session.add(existing)
        session.flush()
        existing_id = existing.id

    snapshots = _snapshots()
    snapshots["plants_flowering"] = []
    snapshots["harvests"] = []
    result = MetrcWorkspaceHydrationService(engine).hydrate(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="MC281234",
        actor="admin",
        resource_snapshots=snapshots,
    )["workspaces"]["cultivation"]

    assert result["created_plants"] == 0
    assert result["warning_count"] >= 1
    assert result["authoritative_reconciliation"]["plant_updates"] == 1
    with Session(engine) as session:
        plant = session.get(CultivationPlant, existing_id)
        assert plant.phase == "vegetative"
        assert plant.strain_name == "GMO"
        assert plant.room_code == "VEG 1"
        assert plant.notes == "Keep local note"
        link = session.scalar(select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.entity_type == "cultivation_plant",
            TraceabilityObjectLink.entity_id == existing_id,
        ))
        assert link is not None
        assert link.provider_resource == "plants"
        assert link.provider_id == "plant-1"
        assert link.status == "verified"
