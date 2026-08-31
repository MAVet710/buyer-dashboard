from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.cultivation.batch_models import CultivationPlantGroup, CultivationPlantGroupMember, CultivationPlantParentLink
from modules.cultivation.batches import CultivationBatchService
from modules.cultivation.models import CultivationPlant, CultivationPlantEvent
from modules.cultivation.service import CultivationService


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-grow", name="Grow Org", slug="grow-org"))
        session.add(Organization(id="org-other", name="Other Org", slug="other-org"))
        session.add_all(
            [
                Facility(
                    id="facility-grow",
                    organization_id="org-grow",
                    name="Cultivation",
                    code="CULT",
                    cultivation_enabled=True,
                    production_enabled=False,
                ),
                Facility(
                    id="facility-other",
                    organization_id="org-other",
                    name="Other Cultivation",
                    code="OTHER",
                    cultivation_enabled=True,
                ),
            ]
        )
        source_product = Product(
            id="source-product",
            organization_id="org-grow",
            sku="GENETICS-SOURCE",
            name="Genetics Source",
            item_type="cannabis",
            base_unit="g",
        )
        session.add(source_product)
        session.flush()
        source_lot = InventoryLot(
            id="source-lot",
            organization_id="org-grow",
            facility_id="facility-grow",
            product_id=source_product.id,
            lot_code="SOURCE-LOT-001",
            compliance_package_id="PKG-SOURCE-001",
            location_code="NURSERY",
            status="available",
        )
        session.add(source_lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id="org-grow",
                facility_id="facility-grow",
                lot_id=source_lot.id,
                transaction_type="receipt",
                quantity_delta=100,
                unit="g",
                actor="seed",
            )
        )
    return engine


def _mother(engine):
    return CultivationService(engine).create_plant(
        "org-grow",
        "facility-grow",
        plant_tag="MOTHER-GG4-001",
        strain_name="GG4",
        phase="vegetative",
        room_code="MOTHER",
        actor="grower",
    )


def test_clone_group_creates_many_plants_atomically_with_real_mother_and_source_genealogy():
    engine = _engine()
    mother = _mother(engine)
    service = CultivationBatchService(engine)
    group = service.create_group(
        "org-grow",
        "facility-grow",
        group_code="GG4-CLONES-01",
        group_type="clone_batch",
        strain_name="GG4",
        quantity=25,
        room_code="NURSERY-A",
        mother_plant_id=mother.id,
        source_lot_id="source-lot",
        tag_prefix="GG4-C01",
        actor="grower",
    )

    assert group["plant_count"] == 25
    assert group["phase_counts"] == {"clone": 25}
    assert group["mother_plant_id"] == mother.id
    assert group["mother_plant_tag"] == mother.plant_tag
    assert group["source_lot_id"] == "source-lot"
    assert group["plants"][0]["plant_tag"] == "GG4-C01-0001"
    assert group["plants"][-1]["plant_tag"] == "GG4-C01-0025"

    lineage = service.plant_lineage("org-grow", "facility-grow", group["plants"][0]["id"])
    assert lineage["group"]["group_code"] == "GG4-CLONES-01"
    assert lineage["mother"]["id"] == mother.id
    assert lineage["source_lot"]["lot_code"] == "SOURCE-LOT-001"
    assert lineage["source_lot"]["compliance_package_id"] == "PKG-SOURCE-001"

    with Session(engine) as session:
        assert session.scalar(select(CultivationPlantGroup).where(CultivationPlantGroup.group_code == "GG4-CLONES-01")) is not None
        assert len(list(session.scalars(select(CultivationPlantGroupMember).where(CultivationPlantGroupMember.group_id == group["id"])))) == 25
        assert len(list(session.scalars(select(CultivationPlantParentLink).where(CultivationPlantParentLink.parent_plant_id == mother.id)))) == 25
        assert len(list(session.scalars(select(CultivationPlantEvent).where(CultivationPlantEvent.event_type == "created_in_group")))) == 25


def test_group_creation_rolls_back_everything_when_one_tag_conflicts():
    engine = _engine()
    CultivationService(engine).create_plant(
        "org-grow",
        "facility-grow",
        plant_tag="DUPLICATE-TAG",
        strain_name="GG4",
        phase="clone",
        room_code="NURSERY",
        actor="grower",
    )
    service = CultivationBatchService(engine)
    with pytest.raises(ValueError, match="already exist"):
        service.create_group(
            "org-grow",
            "facility-grow",
            group_code="ROLLBACK-01",
            group_type="clone_batch",
            strain_name="GG4",
            quantity=2,
            plant_tags=["NEW-TAG", "DUPLICATE-TAG"],
            actor="grower",
        )
    with Session(engine) as session:
        assert session.scalar(select(CultivationPlantGroup).where(CultivationPlantGroup.group_code == "ROLLBACK-01")) is None
        assert session.scalar(select(CultivationPlant).where(CultivationPlant.plant_tag == "NEW-TAG")) is None


def test_batch_transition_moves_every_plant_and_preserves_individual_events():
    engine = _engine()
    service = CultivationBatchService(engine)
    group = service.create_group(
        "org-grow",
        "facility-grow",
        group_code="BATCH-MOVE",
        group_type="clone_batch",
        strain_name="Blue Dream",
        quantity=12,
        room_code="NURSERY-A",
        actor="grower",
    )
    moved = service.transition_group(
        "org-grow",
        "facility-grow",
        group["id"],
        actor="grower",
        phase="vegetative",
        room_code="VEG-1",
        reason="Nursery release",
    )
    assert moved["phase_counts"] == {"vegetative": 12}
    assert moved["room_code"] == "VEG-1"
    assert moved["group_type"] == "vegetative"
    with Session(engine) as session:
        phase_events = list(session.scalars(select(CultivationPlantEvent).where(CultivationPlantEvent.event_type == "phase_changed")))
        room_events = list(session.scalars(select(CultivationPlantEvent).where(CultivationPlantEvent.event_type == "room_moved")))
        assert len(phase_events) == 12
        assert len(room_events) == 12
        assert all(row.reason == "Nursery release" for row in phase_events + room_events)


def test_batch_transition_fails_atomically_when_room_capacity_would_be_exceeded():
    engine = _engine()
    CultivationService(engine).upsert_room(
        "org-grow",
        "facility-grow",
        room_code="VEG-TIGHT",
        display_name="Tight Veg",
        phase="vegetative",
        plant_capacity=5,
    )
    service = CultivationBatchService(engine)
    group = service.create_group(
        "org-grow",
        "facility-grow",
        group_code="CAPACITY-BATCH",
        group_type="clone_batch",
        strain_name="Wedding Cake",
        quantity=6,
        room_code="NURSERY",
        actor="grower",
    )
    with pytest.raises(ValueError, match="capacity would be exceeded"):
        service.transition_group(
            "org-grow",
            "facility-grow",
            group["id"],
            actor="grower",
            phase="vegetative",
            room_code="VEG-TIGHT",
        )
    detail = service.group_detail("org-grow", "facility-grow", group["id"])
    assert detail["phase_counts"] == {"clone": 6}
    assert {row["room_code"] for row in detail["plants"]} == {"NURSERY"}


def test_mother_and_source_links_fail_closed_across_tenants_and_strains():
    engine = _engine()
    service = CultivationBatchService(engine)
    mother = _mother(engine)
    with pytest.raises(ValueError, match="strain must match"):
        service.create_group(
            "org-grow",
            "facility-grow",
            group_code="WRONG-STRAIN",
            group_type="clone_batch",
            strain_name="Not GG4",
            quantity=2,
            mother_plant_id=mother.id,
            actor="grower",
        )
    other = CultivationService(engine).create_plant(
        "org-other",
        "facility-other",
        plant_tag="OTHER-MOTHER",
        strain_name="GG4",
        phase="vegetative",
        room_code="MOTHER",
        actor="other",
    )
    with pytest.raises(ValueError, match="not found in the active cultivation facility"):
        service.create_group(
            "org-grow",
            "facility-grow",
            group_code="CROSS-TENANT",
            group_type="clone_batch",
            strain_name="GG4",
            quantity=2,
            mother_plant_id=other.id,
            actor="grower",
        )


def test_cultivation_group_api_creates_batch_and_exposes_plant_lineage():
    engine = _engine()
    mother = _mother(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": "org-grow",
        "X-Facility-Id": "facility-grow",
        "X-User-Id": "operator",
        "X-User-Role": "operator",
    }
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/inventory/production/plants/groups",
            headers=headers,
            json={
                "group_code": "API-CLONES-01",
                "group_type": "clone_batch",
                "strain_name": "GG4",
                "quantity": 3,
                "room_code": "NURSERY",
                "mother_plant_id": mother.id,
                "source_lot_id": "source-lot",
                "tag_prefix": "API-GG4",
            },
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["plant_count"] == 3
        groups = client.get("/api/v1/inventory/production/plants/groups", headers=headers)
        assert groups.status_code == 200, groups.text
        assert groups.json()["items"][0]["group_code"] == "API-CLONES-01"
        plant_id = payload["plants"][0]["id"]
        lineage = client.get(f"/api/v1/inventory/production/plants/{plant_id}/lineage", headers=headers)
        assert lineage.status_code == 200, lineage.text
        assert lineage.json()["mother"]["plant_tag"] == "MOTHER-GG4-001"
    finally:
        app.dependency_overrides.clear()
