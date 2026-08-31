from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.cultivation.models import CultivationPlant
from modules.cultivation.service import CultivationService
from modules.operational_moats.models import CultivationHarvest


ROOT = Path(__file__).resolve().parents[1]


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _scope(engine):
    with Session(engine) as session, session.begin():
        org = Organization(name="Cultivator", slug="cultivator")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Grow One",
            code="GROW-1",
            cultivation_enabled=True,
            production_enabled=False,
            retail_enabled=False,
        )
        session.add(facility)
        session.flush()
        return org.id, facility.id


def test_room_capacity_and_phase_fit_are_derived_from_live_plants():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    service = CultivationService(engine)
    room = service.upsert_room(
        organization_id,
        facility_id,
        room_code="FLOWER-A",
        display_name="Flower A",
        phase="flowering",
        plant_capacity=2,
        square_feet=240,
        target_cycle_days=63,
    )
    service.create_plant(organization_id, facility_id, plant_tag="P-1", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester", estimated_harvest_date=date(2026, 9, 10))
    service.create_plant(organization_id, facility_id, plant_tag="P-2", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester", estimated_harvest_date=date(2026, 9, 12))
    service.create_plant(organization_id, facility_id, plant_tag="P-3", strain_name="GMO", phase="vegetative", room_code="FLOWER-A", actor="tester")

    current = next(row for row in service.list_rooms(organization_id, facility_id) if row["id"] == room["id"])
    assert current["active_plants"] == 3
    assert current["plant_capacity"] == 2
    assert current["over_capacity"] is True
    assert current["utilization_pct"] == 150.0
    assert current["phase_mismatch_count"] == 1
    assert current["next_estimated_harvest"] == "2026-09-10"


def test_harvest_360_reuses_canonical_harvest_table_and_tracks_yield_and_cogs():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    service = CultivationService(engine)
    first = service.create_plant(organization_id, facility_id, plant_tag="P-10", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester")
    second = service.create_plant(organization_id, facility_id, plant_tag="P-11", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester")

    harvest = service.create_harvest(
        organization_id,
        facility_id,
        harvest_code="HARV-001",
        plant_ids=[first.id, second.id],
        actor="tester",
    )
    assert harvest["status"] == "planned"
    assert harvest["plant_count"] == 2
    assert harvest["strain_name"] == "GMO"
    assert harvest["room_code"] == "FLOWER-A"

    with Session(engine) as session:
        canonical = session.get(CultivationHarvest, harvest["id"])
        assert canonical is not None
        assert canonical.strain == "GMO"
        assert canonical.room == "FLOWER-A"
        assert canonical.plant_count == 2

    service.add_cost(organization_id, facility_id, entity_type="harvest", entity_id=harvest["id"], cost_type="labor", description="Harvest crew", quantity=4, unit="hr", unit_cost=25, actor="tester")
    service.add_cost(organization_id, facility_id, entity_type="harvest", entity_id=harvest["id"], cost_type="material", description="Drying supplies", amount=50, actor="tester")
    active = service.transition_harvest(organization_id, facility_id, harvest["id"], status="active", actor="tester", wet_weight=1000, unit="g")
    assert active["status"] == "active"
    assert active["labor_hours"] == 4.0

    with Session(engine) as session:
        phases = list(session.scalars(select(CultivationPlant.phase).where(CultivationPlant.id.in_([first.id, second.id]))))
    assert phases == ["harvested", "harvested"]

    drying = service.transition_harvest(organization_id, facility_id, harvest["id"], status="drying", actor="tester", dry_weight=250, waste_weight=75, unit="grams")
    assert drying["dry_yield_pct"] == 25.0
    assert drying["labor_cost_usd"] == 100.0
    assert drying["material_cost_usd"] == 50.0
    assert drying["total_cogs_usd"] == 150.0
    assert drying["cost_per_dry_unit"] == 0.6

    with pytest.raises(ValueError, match="Allocate the measured dry-basis harvest output"):
        service.transition_harvest(organization_id, facility_id, harvest["id"], status="completed", actor="tester")


def test_started_harvest_cannot_be_cancelled_after_plants_are_retired():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    service = CultivationService(engine)
    plant = service.create_plant(organization_id, facility_id, plant_tag="P-20", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester")
    harvest = service.create_harvest(organization_id, facility_id, harvest_code="HARV-002", plant_ids=[plant.id], actor="tester")
    service.transition_harvest(organization_id, facility_id, harvest["id"], status="active", actor="tester")
    with pytest.raises(ValueError, match="cannot move from active to cancelled"):
        service.transition_harvest(organization_id, facility_id, harvest["id"], status="cancelled", actor="tester")


def test_planned_harvest_can_be_cancelled_without_retiring_plants():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    service = CultivationService(engine)
    plant = service.create_plant(organization_id, facility_id, plant_tag="P-30", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester")
    harvest = service.create_harvest(organization_id, facility_id, harvest_code="HARV-003", plant_ids=[plant.id], actor="tester")
    cancelled = service.transition_harvest(organization_id, facility_id, harvest["id"], status="cancelled", actor="tester")
    assert cancelled["status"] == "cancelled"
    with Session(engine) as session:
        current = session.get(CultivationPlant, plant.id)
        assert current is not None
        assert current.phase == "flowering"
        assert current.retired_at is None


def test_harvest_weights_are_canonical_grams():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    service = CultivationService(engine)
    plant = service.create_plant(organization_id, facility_id, plant_tag="P-40", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester")
    harvest = service.create_harvest(organization_id, facility_id, harvest_code="HARV-004", plant_ids=[plant.id], actor="tester")
    with pytest.raises(ValueError, match="canonical harvest weights in grams"):
        service.transition_harvest(organization_id, facility_id, harvest["id"], status="active", actor="tester", wet_weight=2, unit="lb")


def test_harvest_operations_do_not_import_or_dispatch_metrc_writes():
    service_source = (ROOT / "modules" / "cultivation" / "service.py").read_text(encoding="utf-8")
    component_source = (ROOT / "frontend" / "src" / "components" / "CultivationOperationsControl.tsx").read_text(encoding="utf-8")
    assert "metrc_" not in service_source.casefold()
    assert "TraceabilityDispatcher" not in service_source
    assert "No Metrc harvest mutation is issued from Harvest 360" in component_source
    assert "Metrc plant/harvest writes remain separately fail-closed" in component_source


def test_cultivation_api_and_frontend_expose_room_harvest_and_cost_depth_without_recreating_harvest_table():
    router = (ROOT / "backend" / "app" / "routers" / "plants.py").read_text(encoding="utf-8")
    plant_ui = (ROOT / "frontend" / "src" / "components" / "PlantInventory.tsx").read_text(encoding="utf-8")
    operations_ui = (ROOT / "frontend" / "src" / "components" / "CultivationOperationsControl.tsx").read_text(encoding="utf-8")
    migration = (ROOT / "migrations" / "versions" / "0057_cultivation_operations.py").read_text(encoding="utf-8")
    models = (ROOT / "modules" / "cultivation" / "models.py").read_text(encoding="utf-8")
    for route in ('@router.get("/rooms")', '@router.post("/rooms")', '@router.get("/harvests")', '@router.post("/harvests"', '@router.post("/costs"'):
        assert route in router
    assert "CultivationOperationsControl" in plant_ui
    assert "HARVEST 360" in operations_ui
    assert "Room Capacity" in operations_ui
    assert "Cultivation COGS" in operations_ui
    assert 'revision = "0057_cultivation_operations"' in migration
    assert 'down_revision = "0056_trace_reconciliation"' in migration
    assert 'op.create_table(\n        "cultivation_harvests"' not in migration
    assert 'class CultivationHarvest(' not in models
    assert 'from modules.operational_moats.models import CultivationHarvest' in (ROOT / "modules" / "cultivation" / "service.py").read_text(encoding="utf-8")
