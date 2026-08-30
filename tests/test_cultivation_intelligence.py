from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services.cultivation_intelligence import CultivationIntelligenceService
from modules.coman.models import Base, Facility, Organization
from modules.cultivation.service import CultivationService


ROOT = Path(__file__).resolve().parents[1]


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _scope(engine):
    with Session(engine) as session, session.begin():
        org = Organization(name="Forecast Grow", slug="forecast-grow")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Grow Forecast",
            code="GROW-F",
            cultivation_enabled=True,
            production_enabled=False,
            retail_enabled=False,
        )
        session.add(facility)
        session.flush()
        return org.id, facility.id


def test_completed_harvest_actuals_drive_dry_supply_forecast():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    ops = CultivationService(engine)
    for index in range(2):
        ops.create_plant(organization_id, facility_id, plant_tag=f"H-{index}", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester")
    plants = ops.list_plants(organization_id, facility_id, phase="flowering")
    harvest = ops.create_harvest(organization_id, facility_id, harvest_code="HIST-1", plant_ids=[row.id for row in plants], actor="tester")
    ops.transition_harvest(organization_id, facility_id, harvest["id"], status="active", actor="tester", wet_weight=1000, unit="g")
    ops.transition_harvest(organization_id, facility_id, harvest["id"], status="completed", actor="tester", dry_weight=300, unit="g")

    for index in range(3):
        ops.create_plant(
            organization_id,
            facility_id,
            plant_tag=f"F-{index}",
            strain_name="GMO",
            phase="flowering",
            room_code="FLOWER-B",
            actor="tester",
            estimated_harvest_date=date(2026, 9, 14),
        )

    forecast = CultivationIntelligenceService(engine).snapshot(organization_id, facility_id, as_of=date(2026, 8, 30))
    assert forecast["yield_model"]["sample_count"] == 1
    assert forecast["yield_model"]["overall_dry_weight_per_plant"] == 150.0
    row = next(item for item in forecast["supply_forecast"] if item["strain"] == "GMO")
    assert row["plants"] == 3
    assert row["estimated_dry_weight"] == 450.0
    assert row["confidence"] == "medium"
    assert forecast["production_handoff"][0]["source"] == "cultivation_forecast"


def test_nursery_forecast_allocates_each_pipeline_plant_once_and_surfaces_future_shortage():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    ops = CultivationService(engine)
    ops.upsert_room(organization_id, facility_id, room_code="FLOWER-A", display_name="Flower A", phase="flowering", plant_capacity=2, target_cycle_days=28)
    ops.create_plant(organization_id, facility_id, plant_tag="FLOW-1", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester", estimated_harvest_date=date(2026, 9, 7))
    ops.create_plant(organization_id, facility_id, plant_tag="FLOW-2", strain_name="GMO", phase="flowering", room_code="FLOWER-A", actor="tester", estimated_harvest_date=date(2026, 9, 7))
    ops.create_plant(organization_id, facility_id, plant_tag="VEG-1", strain_name="GMO", phase="vegetative", room_code="VEG-A", actor="tester")
    ops.create_plant(organization_id, facility_id, plant_tag="VEG-2", strain_name="GMO", phase="vegetative", room_code="VEG-A", actor="tester")

    forecast = CultivationIntelligenceService(engine).snapshot(organization_id, facility_id, as_of=date(2026, 8, 30))
    turns = [row for row in forecast["nursery_forecast"] if row["room_code"] == "FLOWER-A"]
    assert len(turns) >= 2
    assert turns[0]["required_transplants"] == 2
    assert turns[0]["allocated_from_pipeline"] == 2
    assert turns[0]["shortage_plants"] == 0
    assert turns[1]["allocated_from_pipeline"] == 0
    assert turns[1]["shortage_plants"] == 2
    assert forecast["metrics"]["nursery_shortage_plants"] >= 2
    assert forecast["metrics"]["rooms_at_pipeline_risk"] == 1


def test_forecast_core_is_deterministic_and_never_mutates_provider_or_purchasing_state():
    source = (ROOT / "backend" / "app" / "services" / "cultivation_intelligence.py").read_text(encoding="utf-8")
    assert "requests." not in source
    assert "ProviderRouter" not in source
    assert "TraceabilityDispatcher" not in source
    assert '"deterministic_only": True' in source
    assert '"provider_write": False' in source
    assert '"creates_purchase_orders": False' in source


def test_cultivation_intelligence_endpoint_and_ui_are_exposed():
    router = (ROOT / "backend" / "app" / "routers" / "cultivation_intelligence.py").read_text(encoding="utf-8")
    registration = (ROOT / "backend" / "app" / "routers" / "receiving_preflight.py").read_text(encoding="utf-8")
    component = (ROOT / "frontend" / "src" / "components" / "CultivationIntelligencePanel.tsx").read_text(encoding="utf-8")
    plant_inventory = (ROOT / "frontend" / "src" / "components" / "PlantInventory.tsx").read_text(encoding="utf-8")
    assert '@router.get("/intelligence")' in router
    assert "require_facility_capability(context, engine, \"cultivation\")" in router
    assert "router.include_router(cultivation_intelligence_router)" in registration
    assert '"/api/v1/inventory/production/plants/intelligence"' in component
    assert "Supply & Nursery Forecast" in component
    assert "CultivationIntelligencePanel" in plant_inventory
