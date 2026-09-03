from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest

from modules.coman.models import Base, Facility, Organization
from modules.cultivation.post_harvest import PostHarvestService
from modules.cultivation.service import CultivationService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _scope(engine):
    with Session(engine) as session, session.begin():
        org = Organization(name="Post Harvest Cultivator", slug="post-harvest-cultivator")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Grow One",
            code="GROW-PH",
            cultivation_enabled=True,
            production_enabled=False,
            retail_enabled=False,
        )
        session.add(facility)
        session.flush()
        return org.id, facility.id


def _drying_harvest(engine, organization_id, facility_id):
    cultivation = CultivationService(engine)
    plant = cultivation.create_plant(
        organization_id,
        facility_id,
        plant_tag="PH-PLANT-1",
        strain_name="GMO",
        phase="flowering",
        room_code="FLOWER-A",
        actor="cultivator",
    )
    harvest = cultivation.create_harvest(
        organization_id,
        facility_id,
        harvest_code="PH-HARV-1",
        plant_ids=[plant.id],
        actor="cultivator",
    )
    cultivation.transition_harvest(
        organization_id,
        facility_id,
        harvest["id"],
        status="active",
        actor="cultivator",
        wet_weight=1000,
        unit="g",
    )
    return cultivation.transition_harvest(
        organization_id,
        facility_id,
        harvest["id"],
        status="drying",
        actor="cultivator",
        dry_weight=250,
        unit="g",
    )


def test_open_harvest_sync_is_idempotent_and_tracks_drying_stage():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    harvest = _drying_harvest(engine, organization_id, facility_id)
    service = PostHarvestService(engine)

    first = service.sync_open_harvests(organization_id, facility_id, actor="trim-lead")
    second = service.sync_open_harvests(organization_id, facility_id, actor="trim-lead")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0]["id"] == second[0]["id"]
    assert first[0]["harvest_id"] == harvest["id"]
    assert first[0]["stage"] == "drying"
    assert first[0]["wet_weight_g"] == 1000
    assert first[0]["dry_weight_g"] == 250


def test_trim_operator_weight_updates_are_append_only_and_latest_value_drives_current_state():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    _drying_harvest(engine, organization_id, facility_id)
    service = PostHarvestService(engine)
    batch = service.sync_open_harvests(organization_id, facility_id, actor="trim-lead")[0]
    service.transition(organization_id, facility_id, batch["id"], stage="bucking", actor="trim-lead", location_code="TRIM-1")
    service.transition(organization_id, facility_id, batch["id"], stage="trimming", actor="trim-lead", location_code="TRIM-1")

    service.record_weights(
        organization_id,
        facility_id,
        batch["id"],
        actor="trim-operator-a",
        measurements=[
            {"weight_type": "finished_flower", "quantity_g": 80, "container_code": "BIN-1", "note": "First table"},
            {"weight_type": "trim", "quantity_g": 20, "container_code": "BIN-2", "note": "First table"},
            {"weight_type": "wip", "quantity_g": 150, "container_code": "TOTE-1", "note": "Remaining"},
        ],
    )
    detail = service.record_weights(
        organization_id,
        facility_id,
        batch["id"],
        actor="trim-operator-a",
        measurements=[
            {"weight_type": "finished_flower", "quantity_g": 125, "container_code": "BIN-1", "note": "Mid-shift update"},
            {"weight_type": "trim", "quantity_g": 35, "container_code": "BIN-2", "note": "Mid-shift update"},
            {"weight_type": "wip", "quantity_g": 90, "container_code": "TOTE-1", "note": "Remaining"},
        ],
    )

    assert detail["current_weights"]["finished_flower"] == 125
    assert detail["current_weights"]["trim"] == 35
    assert detail["current_weights"]["wip"] == 90
    assert detail["remaining_wip_g"] == 90
    assert detail["weight_event_count"] == 6
    flower_history = [row for row in detail["weight_history"] if row["weight_type"] == "finished_flower"]
    assert [row["quantity_g"] for row in reversed(flower_history)] == [80, 125]
    assert all(row["actor"] == "trim-operator-a" for row in flower_history)


def test_post_harvest_is_forward_only_and_ready_weights_lock_for_normal_operator():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    _drying_harvest(engine, organization_id, facility_id)
    service = PostHarvestService(engine)
    batch = service.sync_open_harvests(organization_id, facility_id, actor="lead")[0]

    with pytest.raises(ValueError, match="forward-only"):
        service.transition(organization_id, facility_id, batch["id"], stage="harvested", actor="operator")

    for stage in ("bucking", "trimming", "curing", "testing_hold"):
        service.transition(organization_id, facility_id, batch["id"], stage=stage, actor="operator")
    service.record_weights(
        organization_id,
        facility_id,
        batch["id"],
        actor="operator",
        measurements=[
            {"weight_type": "finished_flower", "quantity_g": 180},
            {"weight_type": "trim", "quantity_g": 50},
            {"weight_type": "waste", "quantity_g": 20},
        ],
    )
    ready = service.transition(organization_id, facility_id, batch["id"], stage="ready", actor="operator")
    assert ready["stage"] == "ready"

    with pytest.raises(ValueError, match="locked"):
        service.record_weights(
            organization_id,
            facility_id,
            batch["id"],
            actor="operator",
            measurements=[{"weight_type": "finished_flower", "quantity_g": 181}],
        )

    with pytest.raises(ValueError, match="correction reason"):
        service.record_weights(
            organization_id,
            facility_id,
            batch["id"],
            actor="supervisor",
            allow_locked_correction=True,
            measurements=[{"weight_type": "finished_flower", "quantity_g": 181}],
        )

    corrected = service.record_weights(
        organization_id,
        facility_id,
        batch["id"],
        actor="supervisor",
        allow_locked_correction=True,
        correction_reason="Scale transcription correction",
        measurements=[{"weight_type": "finished_flower", "quantity_g": 181}],
    )
    assert corrected["current_weights"]["finished_flower"] == 181
    assert corrected["weight_history"][0]["correction_reason"] == "Scale transcription correction"
    assert any(row["quantity_g"] == 180 for row in corrected["weight_history"] if row["weight_type"] == "finished_flower")


def test_post_harvest_frontend_keeps_operator_surface_simple_and_audit_depth_underneath():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cultivation_page = (root / "frontend" / "src" / "pages" / "CultivationOpsPage.tsx").read_text(encoding="utf-8")
    post_harvest_page = (root / "frontend" / "src" / "pages" / "PostHarvestPage.tsx").read_text(encoding="utf-8")
    handoff = (root / "frontend" / "src" / "components" / "PostHarvestHandoffSummary.tsx").read_text(encoding="utf-8")
    ui = (root / "frontend" / "src" / "components" / "PostHarvestBoard.tsx").read_text(encoding="utf-8")
    shell = (root / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    routes = (root / "frontend" / "src" / "lib" / "workspaceRoutes.ts").read_text(encoding="utf-8")
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    router = (root / "backend" / "app" / "routers" / "production_mutations.py").read_text(encoding="utf-8")

    assert "<PostHarvestBoard />" not in cultivation_page
    assert "<PostHarvestHandoffSummary" in cultivation_page
    assert "<PostHarvestBoard />" in post_harvest_page
    assert 'onNavigate("Post-Harvest")' in cultivation_page
    assert "Needs attention" in handoff
    assert "Ready for trim" in handoff
    assert '{ label: "Post-Harvest", page: "Post-Harvest" }' in shell
    assert '{ page: "Post-Harvest", path: "/cultivation/post-harvest" }' in routes
    assert 'page === "Post-Harvest" ? <PostHarvestPage />' in app
    for label in ("Needs Attention", "Drying", "Ready for Trim", "Trimming", "Curing", "Testing / Hold", "Ready"):
        assert label in ui
    for label in ("Update weights", "Remaining / WIP (g)", "Finished flower (g)", "Trim (g)", "Biomass (g)", "Waste (g)"):
        assert label in ui
    assert "Historical readings are never edited" in ui
    assert "Correct locked weights" in ui
    assert 'managerRoles = new Set(["dev", "admin", "supervisor", "qa"])' in ui
    assert '@cultivation_router.post("/post-harvest/{batch_id}/weights")' in router
    assert 'context.role.casefold() in {"dev", "admin", "supervisor", "qa"}' in router
