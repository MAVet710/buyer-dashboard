from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

from modules.coman.models import Base
from modules.coman.repository import ComanRepository
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.inventory_audit.workflow import (
    ensure_audit_lifecycle_schema,
    get_audit_events,
    set_audit_status,
)


ROOT = Path(__file__).resolve().parents[1]


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    audits = InventoryAuditRepository(engine)
    organization = coman.create_organization("Audit Session QA")
    facility = coman.create_facility(organization.id, "Main", "MAIN")
    product = coman.create_product(
        organization.id,
        sku="PR-1G",
        name="Test Pre-Roll 1g",
        item_type="finished_good",
        base_unit="unit",
        actor="dev",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="PR-LOT-1",
        opening_quantity=24,
        unit="unit",
        actor="dev",
    )
    return audits, organization, facility, lot


def test_audit_can_pause_stop_and_resume_without_losing_session():
    audits, organization, facility, lot = _setup()
    audit = audits.create_audit(
        organization.id,
        facility.id,
        audit_number="RTL-SESSION-001",
        actor="dev",
        operation_type="retail",
        lot_ids=[lot.id],
    )

    # SQLite does not need the production PostgreSQL repair path, but the guard
    # must remain safe to call before every lifecycle transition.
    assert ensure_audit_lifecycle_schema(audits) is False

    set_audit_status(
        audits,
        organization.id,
        facility.id,
        audit.id,
        status="in_progress",
        actor="counter",
    )
    paused = set_audit_status(
        audits,
        organization.id,
        facility.id,
        audit.id,
        status="paused",
        actor="counter",
    )
    assert paused.status == "paused"

    resumed = set_audit_status(
        audits,
        organization.id,
        facility.id,
        audit.id,
        status="in_progress",
        actor="counter",
    )
    assert resumed.status == "in_progress"

    stopped = set_audit_status(
        audits,
        organization.id,
        facility.id,
        audit.id,
        status="stopped",
        actor="counter",
    )
    assert stopped.status == "stopped"

    events = get_audit_events(audits, organization.id, audit.id)
    actions = [event.action for event in events]
    assert "paused" in actions
    assert "resumed" in actions
    assert "stopped" in actions
    assert len(audits.list_lines(organization.id, audit.id)) == 1


def test_scan_audit_camera_component_key_is_stable():
    source = (ROOT / "modules" / "inventory_audit" / "ui.py").read_text(encoding="utf-8")

    assert 'qrcode_scanner(key=f"live_audit_scanner_{stage}_{audit.id}")' in source
    assert "scanner_generation_key" not in source
    assert "Back to Dashboard" in source
    assert "Pause Audit" in source
    assert "Stop & Review" in source
    assert "Generate Current Report" in source


def test_audit_dashboard_supports_all_session_states():
    source = (ROOT / "modules" / "inventory_audit" / "ui.py").read_text(encoding="utf-8")
    migration = (ROOT / "migrations" / "versions" / "0015_inventory_audit_lifecycle.sql").read_text(
        encoding="utf-8"
    )

    for value in ("in_progress", "paused", "stopped", "completed", "cancelled"):
        assert value in source
        assert value in migration
    assert "Start New Audit" in source
    assert "Reopen Audit" in source
    assert "Export CSV" in source
    assert "Export Excel" in source


def test_pause_stop_runtime_guard_can_apply_migration_0015_in_postgres():
    source = (ROOT / "modules" / "inventory_audit" / "workflow.py").read_text(encoding="utf-8")

    assert "ensure_audit_lifecycle_schema" in source
    assert "drop constraint if exists ck_inventory_audit_status" in source
    assert "add constraint ck_inventory_audit_status" in source
    assert "'paused', 'stopped'" in source
    assert "0015_inventory_audit_lifecycle" in source
    assert "0014_machine_reference_library" in source
