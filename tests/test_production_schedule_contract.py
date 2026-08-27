from datetime import datetime, timezone
from pathlib import Path

from modules.production_erp.models import ProductionSchedulePlacement
from modules.production_erp.scheduling import ProductionScheduleService


ROOT = Path(__file__).resolve().parents[1]


def test_schedule_placement_is_versioned_and_auditable():
    constraints = " ".join(str(item) for item in ProductionSchedulePlacement.__table__.constraints)
    assert "production_order_id" in constraints
    assert "version" in constraints
    assert hasattr(ProductionSchedulePlacement, "scheduled_start_at")
    assert hasattr(ProductionSchedulePlacement, "scheduled_end_at")
    assert hasattr(ProductionSchedulePlacement, "machine_id")
    assert hasattr(ProductionSchedulePlacement, "planned_people")
    assert hasattr(ProductionSchedulePlacement, "reason")
    assert hasattr(ProductionSchedulePlacement, "active")
    assert hasattr(ProductionSchedulePlacement, "created_by")


def test_schedule_migration_chains_from_bom_standards_head():
    migration = (
        ROOT / "migrations" / "versions" / "0047_production_schedule_placements.py"
    ).read_text(encoding="utf-8")
    assert 'revision = "0047_prod_schedule"' in migration
    assert 'down_revision = "0046_production_bom_standards"' in migration
    assert '"production_schedule_placements"' in migration
    assert 'sa.UniqueConstraint("production_order_id", "version"' in migration
    assert 'sa.CheckConstraint("scheduled_end_at > scheduled_start_at"' in migration
    assert 'sa.CheckConstraint("planned_people >= 0"' in migration


def test_schedule_preview_is_required_before_authorized_commit():
    router = (
        ROOT / "backend" / "app" / "routers" / "production.py"
    ).read_text(encoding="utf-8")
    scheduling = (
        ROOT / "modules" / "production_erp" / "scheduling.py"
    ).read_text(encoding="utf-8")

    assert '@router.post("/orders/{order_id}/schedule/preview")' in router
    assert '@router.post("/orders/{order_id}/schedule")' in router
    assert '{"dev", "admin", "planner", "supervisor"}' in router
    assert "Your role cannot commit production schedule changes" in router
    assert 'preview_key != preview["preview_key"]' in scheduling
    assert "Schedule preview is stale" in scheduling
    assert ".with_for_update()" in scheduling
    assert '"state_fingerprint": state_fingerprint' in scheduling


def test_calendar_surfaces_conflicts_before_mutation_and_opens_run_360():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    calendar = (
        ROOT / "frontend" / "src" / "components" / "ProductionCalendar.tsx"
    ).read_text(encoding="utf-8")

    assert "<ProductionCalendar onOpenRun={openProductionRun360}/>" in app
    assert "Preview Schedule" in calendar
    assert "Exact Change Preview" in calendar
    assert "I reviewed these conflicts" in calendar
    assert "preview_key: preview.preview_key" in calendar
    assert "accept_warnings: acknowledged" in calendar
    assert "onOpenRun(row.production_order_id)" in calendar
    assert "/schedule/preview" in calendar
    assert "/schedule`" in calendar


def test_calendar_never_mutates_purchasing_for_material_shortages():
    calendar = (
        ROOT / "frontend" / "src" / "components" / "ProductionCalendar.tsx"
    ).read_text(encoding="utf-8").casefold()
    scheduling = (
        ROOT / "modules" / "production_erp" / "scheduling.py"
    ).read_text(encoding="utf-8")

    assert "purchase-orders" not in calendar
    assert "/purchase" not in calendar
    assert "Buyer review required; Production will not create a PO." in scheduling
    assert "material_shortage" in scheduling


def test_preview_fingerprint_changes_when_operational_state_changes():
    base_state = {
        "crew": {"2026-08-27": {"person_hours": 16.0}},
        "materials": [{"product_id": "cart", "potential": 1000.0}],
    }
    changed_state = {
        "crew": {"2026-08-27": {"person_hours": 8.0}},
        "materials": [{"product_id": "cart", "potential": 1000.0}],
    }
    first = ProductionScheduleService._state_fingerprint(base_state)
    second = ProductionScheduleService._state_fingerprint(changed_state)
    assert first != second

    warnings = [{"code": "qa_required", "severity": "warning"}]
    request = {"order_id": "run-1", "state_fingerprint": first}
    changed_request = {"order_id": "run-1", "state_fingerprint": second}
    assert ProductionScheduleService._preview_key(request, warnings) != ProductionScheduleService._preview_key(
        changed_request, warnings
    )


def test_window_capacity_accounts_for_every_calendar_day_touched():
    start = datetime(2026, 8, 27, 20, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 28, 4, 0, tzinfo=timezone.utc)
    by_day = ProductionScheduleService._window_hours_by_day(start, end)
    assert by_day == {"2026-08-27": 4.0, "2026-08-28": 4.0}


def test_resource_category_matching_is_case_insensitive_and_bidirectional():
    assert ProductionScheduleService._category_matches("Filling", "Filling Line")
    assert ProductionScheduleService._category_matches("Rosin Press", "press")
    assert not ProductionScheduleService._category_matches("Extraction", "Packaging")
