from datetime import date, datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_run_history import list_label_run_history
from modules.coman.models import Base, Facility, InventoryTransaction, Organization, Product
from modules.label_studio_workflow import LabelProductionEvent, LabelProductionRun, LabelProductionWorkflowService


@pytest.fixture
def saved_labels():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="History test", slug="history-test")
        other = Organization(name="Other tenant", slug="history-other")
        session.add_all([org, other]); session.flush()
        facility = Facility(organization_id=org.id, name="One", code="ONE", production_enabled=True)
        sibling = Facility(organization_id=org.id, name="Two", code="TWO", production_enabled=True)
        alien = Facility(organization_id=other.id, name="Other", code="OTHER", production_enabled=True)
        product = Product(organization_id=org.id, sku="HISTORY", name="Renamed product", item_type="finished_good", base_unit="unit")
        other_product = Product(organization_id=other.id, sku="OTHER", name="Other", item_type="finished_good", base_unit="unit")
        session.add_all([facility, sibling, alien, product, other_product]); session.flush()
        origin = datetime(2026, 9, 1, tzinfo=timezone.utc)
        snapshot = {"product": {"name": "Original 100% product", "sku": "HISTORY"}, "label": {"product_name": "Original 100% product", "total_thc": "20%"}, "source": {"lot_id": "source", "package_id": "SOURCE-TAG", "lot_code": "OLD-BATCH", "label": {}, "coa": {"overall_status": "pass", "date_tested": "2026-08-01", "results": []}}, "print_layout": {"layout": "compact_single", "width_in": 3.5, "height_in": 2.1, "source_count": 1}, "quantity": 24}
        for index in range(125):
            session.add(LabelProductionRun(id=f"label-{index:03d}", organization_id=org.id, facility_id=facility.id, product_id=product.id, quantity=24, status="archived" if index == 0 else "printed", metrc_package_tag=f"TEST-TAG-{index:03d}", label_snapshot_json=json.dumps(snapshot), created_by="operator", created_at=origin+timedelta(minutes=index)))
        session.add(LabelProductionRun(id="sibling-label", organization_id=org.id, facility_id=sibling.id, product_id=product.id, quantity=24, status="printed", metrc_package_tag="SIBLING-TAG", label_snapshot_json=json.dumps(snapshot), created_by="operator"))
        session.add(LabelProductionRun(id="alien-label", organization_id=other.id, facility_id=alien.id, product_id=other_product.id, quantity=24, status="printed", metrc_package_tag="ALIEN-TAG", label_snapshot_json=json.dumps(snapshot), created_by="operator"))
        session.flush()
        ids = org.id, facility.id, sibling.id, other.id, alien.id
    yield engine, ids, snapshot
    engine.dispose()


def test_history_paginates_old_records_and_searches_snapshots(saved_labels):
    engine, (org, facility, *_), _ = saved_labels
    first = list_label_run_history(engine, org, facility, limit=50)
    last = list_label_run_history(engine, org, facility, limit=50, offset=100)
    assert first["total"] == 125 and first["has_more"]
    assert len(first["items"]) == 50
    assert len(last["items"]) == 25 and not last["has_more"]
    assert not {row["id"] for row in first["items"]} & {row["id"] for row in last["items"]}
    old = list_label_run_history(engine, org, facility, search="TEST-TAG-000")
    assert [row["id"] for row in old["items"]] == ["label-000"]
    assert old["items"][0]["status"] == "archived"
    assert list_label_run_history(engine, org, facility, search="100%")["total"] == 125
    assert list_label_run_history(engine, org, facility, search="OLD-BATCH")["total"] == 125
    assert list_label_run_history(engine, org, facility, search="Renamed product")["total"] == 0


def test_history_is_scoped_and_does_not_hydrate_detail(saved_labels, monkeypatch):
    engine, (org, facility, sibling, other, alien), _ = saved_labels
    monkeypatch.setattr(LabelProductionWorkflowService, "_serialize", lambda *args: pytest.fail("List must not render full label detail"))
    statements = []
    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = list_label_run_history(engine, org, facility)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) <= 3
    assert {row["id"] for row in result["items"]}.isdisjoint({"sibling-label", "alien-label"})
    assert "snapshot" not in result["items"][0] and "events" not in result["items"][0]
    assert list_label_run_history(engine, org, alien)["total"] == 0
    assert list_label_run_history(engine, other, facility)["total"] == 0
    assert list_label_run_history(engine, org, sibling)["total"] == 1


def test_history_filters_dates_status_and_rejects_invalid_ranges(saved_labels):
    engine, (org, facility, *_), _ = saved_labels
    assert list_label_run_history(engine, org, facility, status="archived")["total"] == 1
    assert list_label_run_history(engine, org, facility, created_from=date(2026,9,1), created_to=date(2026,9,1))["total"] == 125
    assert list_label_run_history(engine, org, facility, created_from=date(2026,9,2))["total"] == 0
    for kwargs in ({"limit":0}, {"limit":101}, {"offset":-1}, {"status":"unknown"}, {"created_from":date(2026,9,2),"created_to":date(2026,9,1)}):
        with pytest.raises(ValueError):
            list_label_run_history(engine, org, facility, **kwargs)
    with pytest.raises(ValueError):
        list_label_run_history(engine, "", facility)


def test_reopen_and_reprint_preserve_snapshot_tag_quantity_and_inventory(saved_labels):
    engine, (org, facility, sibling, other, alien), snapshot = saved_labels
    service = LabelProductionWorkflowService(engine)
    before = service.get_run(org, facility, "label-001")
    result = service.record_print(org, facility, "label-001", actor="replacement-operator", copies=2, reason="Two damaged labels")
    assert result["snapshot"] == snapshot == before["snapshot"]
    assert result["quantity"] == before["quantity"] == 24
    assert result["metrc_package_tag"] == before["metrc_package_tag"]
    assert result["status"] == before["status"] == "printed"
    assert result["events"][-1]["event_type"] == "reprinted"
    assert result["events"][-1]["details"] == {"copies":2,"reason":"Two damaged labels"}
    assert LabelProductionWorkflowService(engine).get_run(org, facility, "label-001")["events"][-1]["actor"] == "replacement-operator"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
        assert session.scalar(select(func.count()).select_from(LabelProductionRun)) == 127
        assert session.scalar(select(func.count()).select_from(LabelProductionEvent)) == 1
    for wrong_org, wrong_facility in ((org,sibling),(other,alien),(other,facility)):
        with pytest.raises(ValueError):
            service.get_run(wrong_org,wrong_facility,"label-001")
        with pytest.raises(ValueError):
            service.record_print(wrong_org,wrong_facility,"label-001",actor="other",copies=1,reason="No access")
    with pytest.raises(ValueError):
        service.record_print(org,facility,"label-001",actor="operator",copies=1,reason="")
    with pytest.raises(ValueError):
        service.record_print(org,facility,"label-000",actor="operator",copies=1,reason="Archived")
    history = list_label_run_history(engine,org,facility,search="TEST-TAG-001")
    assert history["items"][0]["print_requests"] == 1
