from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import String, create_engine, event, func, inspect, select
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from modules.coman.models import Base, AuditEvent, CommercialOrder, CommercialOrderLine, InventoryTransaction, TradePartner
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CommercialShipment, CommercialInvoice, CommercialInvoiceLine
from modules.commercial_finance.service import CommercialFinanceService
from modules.wholesale_logistics.models import DispatchRun, DispatchStop
from modules.wholesale_logistics.schemas import RunInput, StopInput
from modules.wholesale_logistics.service import LogisticsService, values


@pytest.fixture
def setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    org = repo.create_organization("Logistics QA")
    facility = repo.create_facility(org.id, "Main", "MAIN")
    other = repo.create_facility(org.id, "Other", "OTHER")
    commercial = CommercialRepository(engine)
    partner = commercial.create_trade_partner(org.id, name="Customer", partner_type="customer", actor="tester", contact_name="Receiver")
    product = repo.create_product(org.id, sku="QA", name="QA", item_type="finished_good", base_unit="unit", actor="tester")
    service = LogisticsService(engine, org.id, facility.id, "tester")
    def shipment(number, target=facility):
        order = commercial.create_order(organization_id=org.id, facility_id=target.id, partner_id=partner.id, order_number=number, order_type="sales", order_date=date.today(), due_date=date.today(), lines=[{"product_id":product.id,"quantity":5,"unit_price":10,"unit":"unit"}], actor="tester")
        return CommercialFinanceService(engine).create_shipment(organization_id=org.id, facility_id=target.id, order_id=order.id, shipment_number=number, actor="tester", manifest_reference="MAN-"+number)
    return engine, service, shipment, other, partner, repo


def run(service):
    return service.create(RunInput(service_date=date.today(), driver_name="Driver", vehicle_license_plate_number="PLATE"))["id"]


def mutate(service, rid, action, payload=None, sid=None):
    return service.mutate(rid, service.detail(rid)["version"], action, payload, sid)


def add(service, rid, shipment, **fields):
    mutate(service, rid, "add", {"shipment_id": shipment.id, "address_snapshot": "10 Main Street", **fields})
    return service.detail(rid)["stops"][-1]["id"]


def status(service, rid, sid, value, **fields):
    return mutate(service, rid, "status", {"status": value, **fields}, sid)


def manifested(engine, shipment):
    with Session(engine) as session, session.begin():
        session.get(CommercialShipment, shipment.id).status = "manifested"


def arrived(engine, service, rid, sid, shipment):
    manifested(engine, shipment)
    for value in ("loaded", "en_route", "arrived"):
        status(service, rid, sid, value)


def test_scope_linking_snapshots_and_duplicate_assignment(setup):
    engine, service, shipment, other, partner, repo = setup
    rid, second = run(service), run(service)
    local, foreign = shipment("A"), shipment("B", other)
    with pytest.raises(ValueError, match="active facility"):
        add(service, rid, foreign)
    sid = add(service, rid, local)
    with pytest.raises(ValueError, match="already belongs"):
        add(service, second, local)
    outsider = LogisticsService(engine, service.org, other.id, "tester")
    assert outsider.board(date.today())["runs"] == []
    with pytest.raises(LookupError):
        outsider.detail(rid)
    with pytest.raises(LookupError):
        outsider.mutate(rid, 2, "plan")
    other_org = repo.create_organization("Other tenant")
    tenant = LogisticsService(engine, other_org.id, other.id, "tester")
    assert tenant.candidates()["shipments"] == []
    with pytest.raises(LookupError):
        tenant.detail(rid)
    with pytest.raises(LookupError):
        mutate(service, second, "remove", sid=sid)
    with Session(engine) as session, session.begin():
        session.get(TradePartner, partner.id).contact_name = "Changed"
    stop = service.detail(rid)["stops"][0]
    assert stop["contact_snapshot"] == "Receiver"
    assert stop["commercial_order_id"] == local.commercial_order_id
    assert stop["partner_id"] == partner.id
    assert stop["manifest_reference"] == "MAN-A"
    assert service.candidates()["shipments"] == []
    mutate(service, rid, "remove", sid=sid)
    add(service, second, local)


def test_planning_coordinates_reordering_stale_version_and_lock(setup):
    engine, service, shipment, *_ = setup
    rid = run(service)
    first = shipment("A")
    a = add(service, rid, first, latitude=0, longitude=0)
    b = add(service, rid, shipment("B"), latitude=0, longitude=10)
    c = add(service, rid, shipment("C"), latitude=0, longitude=1)
    mutate(service, rid, "plan")
    assert [s["id"] for s in service.detail(rid)["stops"]] == [a,c,b]
    mutate(service, rid, "reorder", [b,c,a])
    assert [s["sequence"] for s in service.detail(rid)["stops"]] == [1,2,3]
    with pytest.raises(ValueError, match="exactly once"):
        mutate(service, rid, "reorder", [a,a,b])
    with pytest.raises(ValueError, match="Refresh"):
        service.mutate(rid, 1, "plan")
    status(service, rid, a, "loaded")
    with pytest.raises(ValueError, match="locked"):
        mutate(service, rid, "plan")
    missing = run(service)
    add(service, missing, shipment("D"))
    add(service, missing, shipment("E"), latitude=0, longitude=10)
    add(service, missing, shipment("F"), latitude=0, longitude=1)
    original = service.detail(missing)
    version = service.detail(missing)["version"]
    result = mutate(service, missing, "plan")
    assert "Coordinates missing" in result["message"]
    assert result["version"] == version
    assert service.detail(missing) == original


@pytest.mark.parametrize("outcome", ["delivered", "partial", "rejected"])
def test_delivery_evidence_never_changes_fulfillment_or_inventory(setup, outcome):
    engine, service, shipment, *_ = setup
    rid = run(service)
    sh = shipment("A")
    sid = add(service, rid, sh)
    arrived(engine, service, rid, sid, sh)
    CommercialFinanceService(engine).create_invoice_from_order(
        organization_id=service.org, facility_id=service.facility,
        order_id=sh.commercial_order_id, invoice_number="INV-A", actor="tester")
    with Session(engine) as session:
        finance_before = [[values(row) for row in session.scalars(select(model))]
                          for model in (CommercialInvoice, CommercialInvoiceLine)]
        before = [(l.id,l.fulfilled_quantity) for l in session.scalars(select(CommercialOrderLine))]
        inventory_before = session.scalar(select(func.count()).select_from(InventoryTransaction))
        order_status = session.get(CommercialOrder, sh.commercial_order_id).status
    fields = {"outcome_notes": "Two cases refused"}
    if outcome != "rejected":
        fields.update(recipient_name="Receiver", acknowledgment_name="Receiver", delivered_at=datetime.now(timezone.utc)-timedelta(minutes=1))
    status(service, rid, sid, outcome, **fields)
    original = service.detail(rid)["stops"][0]
    version = service.detail(rid)["version"]
    with Session(engine) as session:
        audit_count = session.scalar(select(func.count()).select_from(AuditEvent))
    status(service, rid, sid, outcome, recipient_name="Cannot overwrite")
    assert service.detail(rid)["stops"][0] == original
    assert service.detail(rid)["version"] == version
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_count
    if outcome in {"partial", "rejected"}:
        status(service, rid, sid, "returned", outcome_notes="Remainder returned for review")
        updated = service.detail(rid)["stops"][0]
        for field in ("delivered_at", "recipient_name", "acknowledgment_name", "acknowledged_at"):
            assert updated[field] == original[field]
        assert "Two cases refused" in updated["outcome_notes"]
        status(service, rid, sid, "returned", outcome_notes="Cannot replace return evidence")
        assert service.detail(rid)["stops"][0] == updated
    with Session(engine) as session:
        assert [[values(row) for row in session.scalars(select(model))]
                for model in (CommercialInvoice, CommercialInvoiceLine)] == finance_before
        assert [(l.id,l.fulfilled_quantity) for l in session.scalars(select(CommercialOrderLine))] == before
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == inventory_before
        canonical = session.get(CommercialShipment, sh.id)
        assert canonical.status == "manifested" and canonical.delivered_at is None
        assert session.get(CommercialOrder, sh.commercial_order_id).status == order_status
        audits = list(session.scalars(select(AuditEvent).where(AuditEvent.entity_id == rid)))
        assert len(audits) >= 6
        assert all(json.loads(a.changes_json)["_event"]["correlation_id"] == f"dispatch:{rid}" for a in audits)


def test_transition_and_pod_validation(setup):
    engine, service, shipment, *_ = setup
    rid = run(service)
    sh = shipment("A")
    sid = add(service, rid, sh)
    with pytest.raises(ValueError, match="Invalid"):
        status(service, rid, sid, "delivered", recipient_name="Receiver")
    status(service, rid, sid, "loaded")
    with pytest.raises(ValueError, match="manifest"):
        status(service, rid, sid, "en_route")
    manifested(engine, sh)
    status(service, rid, sid, "en_route")
    status(service, rid, sid, "arrived")
    with pytest.raises(ValueError, match="Recipient"):
        status(service, rid, sid, "delivered")
    with pytest.raises(ValueError, match="notes"):
        status(service, rid, sid, "rejected")
    with pytest.raises(ValueError, match="future"):
        status(service, rid, sid, "delivered", recipient_name="Receiver", delivered_at=datetime.now(timezone.utc)+timedelta(days=1))
    status(service, rid, sid, "delivered", recipient_name="Receiver")
    assert service.detail(rid)["stops"][0]["delivered_at"]
    with pytest.raises(ValueError, match="Invalid"):
        status(service, rid, sid, "loaded")


def test_input_validation():
    for fields in ({"latitude":0}, {"latitude":float("nan"),"longitude":0}, {"planned_start":"2026-09-25T10:00:00"}, {"planned_start":"2026-09-25T12:00:00Z","planned_end":"2026-09-25T10:00:00Z"}):
        with pytest.raises(ValidationError):
            StopInput(shipment_id="x", address_snapshot="10 Main", **fields)


@pytest.mark.parametrize("size", [1, 25, 100])
def test_bounded_board_and_candidates_no_per_row_queries(setup, size):
    engine, service, shipment, *_ = setup
    rid = run(service)
    for index in range(size):
        add(service, rid, shipment(str(index)))
    queries=[]
    def capture(*args): queries.append(args[2])
    event.listen(engine,"before_cursor_execute",capture)
    try:
        board=service.board(date.today())
        assert len(queries)==2
        assert board["runs"][0]["stop_count"]==size
        queries.clear()
        service.candidates()
        assert len(queries)==1
        queries.clear()
        service.detail(rid)
        assert len(queries)==2
    finally:
        event.remove(engine,"before_cursor_execute",capture)


def test_read_pagination_and_stop_capacity(setup):
    engine, service, shipment, *_ = setup
    rid = run(service)
    first = shipment("PAGES")
    with Session(engine) as session, session.begin():
        run_data = values(session.get(DispatchRun, rid))
        shipment_data = values(session.get(CommercialShipment, first.id))
        session.execute(DispatchRun.__table__.insert(), [
            {**run_data, "id": f"page-run-{index}"} for index in range(100)])
        session.execute(CommercialShipment.__table__.insert(), [
            {**shipment_data, "id": f"page-shipment-{index}", "shipment_number": f"PAGE-{index}"}
            for index in range(200)])
    board = service.board(date.today())
    next_board = service.board(date.today(), offset=100)
    assert len(board["runs"]) == 100 and board["has_more"]
    assert len(next_board["runs"]) == 1 and not next_board["has_more"]
    assert not ({r["id"] for r in board["runs"]} & {r["id"] for r in next_board["runs"]})
    candidates = service.candidates()
    next_candidates = service.candidates(offset=200)
    assert len(candidates["shipments"]) == 200 and candidates["has_more"]
    assert len(next_candidates["shipments"]) == 1 and not next_candidates["has_more"]
    assert not ({s["id"] for s in candidates["shipments"]} & {s["id"] for s in next_candidates["shipments"]})
    sid = add(service, rid, first)
    with Session(engine) as session, session.begin():
        stop_data = values(session.get(DispatchStop, sid))
        session.execute(DispatchStop.__table__.insert(), [
            {**stop_data, "id": f"page-stop-{index}", "shipment_id": f"page-shipment-{index}", "sequence": index+2}
            for index in range(99)])
    with pytest.raises(ValueError, match="at most 100"):
        mutate(service, rid, "add", {"shipment_id": "page-shipment-100", "address_snapshot": "Street"})
    assert len(service.detail(rid)["stops"]) == 100


def test_migration_upgrade_downgrade():
    path=Path(__file__).parents[1]/"migrations/versions/0084_wholesale_logistics.py"
    spec=importlib.util.spec_from_file_location("logistics_migration",path)
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine=create_engine("sqlite://")
    with engine.begin() as connection:
        migration.op=Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert {column["name"] for column in inspect(connection).get_columns("wholesale_dispatch_runs")} == set(DispatchRun.__table__.columns.keys())
        assert {column["name"] for column in inspect(connection).get_columns("wholesale_dispatch_stops")} == set(DispatchStop.__table__.columns.keys())
        migration.downgrade()
        assert "wholesale_dispatch_runs" not in inspect(connection).get_table_names()

def test_api_permissions_and_route_scope(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.auth import RequestContext, get_commercial_context
    from backend.app.database import get_engine
    from backend.app.routers.wholesale_logistics import router
    from sqlalchemy.pool import StaticPool

    # TestClient runs on another thread, so use one shared in-memory connection.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    org = repo.create_organization("API QA")
    facility = repo.create_facility(org.id, "API", "API")
    context = RequestContext(user_id="tester", organization_id=org.id, facility_id=facility.id, role="read_only")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_commercial_context] = lambda: context
    with TestClient(app) as client:
        body = {"service_date":"2026-09-25", "driver_name":"Driver", "vehicle_license_plate_number":"PLATE"}
        assert client.post("/wholesale-logistics/runs/missing/stops/missing/create-reconciliation-work",json={"version":1}).status_code == 403
        assert client.post("/wholesale-logistics/runs",json=body).status_code == 403
        assert client.get("/wholesale-logistics/runs?service_date=2026-09-25").status_code == 200
        context = RequestContext(user_id="tester", organization_id=org.id, facility_id=facility.id, role="dev")
        response = client.post("/wholesale-logistics/runs",json=body)
        assert response.status_code == 200
        rid=response.json()["id"]
        assert client.post(f"/wholesale-logistics/runs/{rid}/plan",json={"version":999}).status_code == 422
        assert client.post(f"/wholesale-logistics/runs/{rid}/stops",json={"version":1,"shipment_id":"unknown","address_snapshot":"Street"}).status_code == 422
        assert client.get("/wholesale-logistics/runs/unknown").status_code == 404
        assert client.post(f"/wholesale-logistics/runs/{rid}/stops/missing/create-reconciliation-work",json={"version":1}).status_code == 404
        from modules.coman.permissions import AppUserPermissionOverride
        context = RequestContext(user_id="tester", organization_id=org.id, facility_id=facility.id, role="buyer")
        with Session(engine) as session, session.begin():
            session.add(AppUserPermissionOverride(user_id="tester", organization_id=org.id, facility_id=facility.id,
                permission="work.create", effect="deny", created_by="test", updated_by="test"))
        assert client.post(f"/wholesale-logistics/runs/{rid}/stops/missing/create-reconciliation-work",json={"version":1}).status_code == 403


def test_real_fulfillment_is_not_duplicated_by_partial_delivery(setup):
    engine, service, shipment, _, _, repo = setup
    sh = shipment("FULFILLED")
    commercial = CommercialRepository(engine)
    with Session(engine) as session:
        line = session.scalar(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id == sh.commercial_order_id))
    lot = repo.create_inventory_lot(service.org, service.facility, product_id=line.product_id, lot_code="SHIP-LOT", actor="tester", opening_quantity=10, unit="unit")
    commercial.confirm_order(sh.commercial_order_id, organization_id=service.org, facility_id=service.facility, actor="tester")
    commercial.allocate_lot(organization_id=service.org, facility_id=service.facility, order_line_id=line.id, lot_id=lot.id, quantity=5, actor="tester")
    manifested(engine, sh)
    commercial.post_fulfillment(organization_id=service.org, facility_id=service.facility, order_line_id=line.id, lot_id=lot.id, quantity=5, actor="tester")
    rid = run(service)
    sid = add(service, rid, sh)
    for state in ("loaded", "en_route", "arrived"):
        status(service, rid, sid, state)
    status(service, rid, sid, "partial", recipient_name="Receiver", outcome_notes="Accepted 3, refused 2")
    status(service, rid, sid, "partial", recipient_name="Receiver", outcome_notes="Accepted 3, refused 2")
    status(service, rid, sid, "returned", outcome_notes="Two returned pending inventory review")
    assert repo.inventory_balance(service.org, lot.id) == 5
    with Session(engine) as session:
        assert session.get(CommercialOrderLine, line.id).fulfilled_quantity == 5
        assert session.get(CommercialOrder, sh.commercial_order_id).status == "fulfilled"
        assert session.scalar(select(func.count()).select_from(InventoryTransaction).where(InventoryTransaction.commercial_order_id == sh.commercial_order_id)) == 1

def test_postgresql_migration_emits_rls_and_browser_acl_guards():
    from io import StringIO
    path = Path(__file__).parents[1] / "migrations/versions/0084_wholesale_logistics.py"
    spec = importlib.util.spec_from_file_location("logistics_pg_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = StringIO()
    migration.op = Operations(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}))
    migration.upgrade()
    sql = output.getvalue()
    for table in ("wholesale_dispatch_runs", "wholesale_dispatch_stops"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC" in sql
    assert "'anon','authenticated'" in sql
    assert "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime')" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.wholesale_dispatch_runs," in sql
    assert "public.wholesale_dispatch_stops TO doobielogic_render_runtime" in sql
    assert "CREATE ROLE" not in sql and "CREATE POLICY" not in sql
    assert "CONSTRAINT uq_dispatch_shipment UNIQUE (shipment_id)" in sql
    assert "FOREIGN KEY(shipment_id) REFERENCES commercial_shipments (id) ON DELETE RESTRICT" in sql
    assert "FOREIGN KEY(work_item_id) REFERENCES doobie_work_items (id) ON DELETE SET NULL" in sql


@pytest.mark.parametrize("snapshots", [{}, {"driver_license_number": None, "vehicle_make": None, "vehicle_model": None},
                                     {"driver_license_number": "", "vehicle_make": "", "vehicle_model": ""},
                                     {"driver_license_number": "DL-123", "vehicle_make": "Ford", "vehicle_model": "Transit"}])
def test_optional_run_snapshots_round_trip_and_planning_lock(setup, snapshots):
    _, service, shipment, *_ = setup
    data = RunInput(service_date=date.today(), driver_name="Driver", vehicle_license_plate_number="PLATE", **snapshots)
    rid = service.create(data)["id"]
    for result in (service.detail(rid), service.board(date.today())["runs"][0]):
        for field in ("driver_license_number", "vehicle_make", "vehicle_model"):
            assert result[field] == snapshots.get(field)
    edited = {**data.model_dump(), "vehicle_model": "Updated snapshot"}
    mutate(service, rid, "edit", edited)
    assert service.detail(rid)["vehicle_model"] == "Updated snapshot"
    sh = shipment("SNAPSHOT")
    sid = add(service, rid, sh)
    status(service, rid, sid, "loaded")
    for action, payload in (("edit", edited), ("remove", None), ("reorder", [sid]), ("plan", None),
                            ("add", {"shipment_id": sh.id, "address_snapshot": "Street"})):
        with pytest.raises(ValueError, match="locked"):
            mutate(service, rid, action, payload, sid if action == "remove" else None)


@pytest.mark.parametrize("outcome", ["partial", "rejected", "returned"])
def test_exceptions_require_nonblank_reconciliation_notes(setup, outcome):
    engine, service, shipment, *_ = setup
    rid = run(service)
    sh = shipment("NOTES")
    sid = add(service, rid, sh)
    arrived(engine, service, rid, sid, sh)
    if outcome == "returned":
        status(service, rid, sid, "rejected", outcome_notes="Refused")
    before = service.detail(rid)
    with pytest.raises(ValueError, match="notes"):
        status(service, rid, sid, outcome, outcome_notes="   ")
    assert service.detail(rid) == before


@pytest.mark.parametrize("manifest_status,reference", [("planned", "MAN"), ("manifested", "  "), ("shipped", "")])
def test_departure_requires_both_governed_manifest_status_and_reference(setup, manifest_status, reference):
    engine, service, shipment, *_ = setup
    rid = run(service)
    sh = shipment("MANIFEST")
    sid = add(service, rid, sh)
    status(service, rid, sid, "loaded")
    with Session(engine) as session, session.begin():
        canonical = session.get(CommercialShipment, sh.id)
        canonical.status, canonical.manifest_reference = manifest_status, reference
    with pytest.raises(ValueError, match="manifest"):
        status(service, rid, sid, "en_route")


@pytest.mark.parametrize("table", ["wholesale_dispatch_runs", "wholesale_dispatch_stops"])
def test_downgrade_preserves_either_table_evidence(table):
    from sqlalchemy import MetaData, Table
    path = Path(__file__).parents[1] / "migrations/versions/0084_wholesale_logistics.py"
    spec = importlib.util.spec_from_file_location("logistics_rollback", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with create_engine("sqlite://").begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        target = Table(table, MetaData(), autoload_with=connection, resolve_fks=False)
        # Isolate each guard, including orphan evidence left by damaged/imported data.
        fields = {column.name: "evidence" for column in target.columns
                  if not column.nullable and isinstance(column.type, String)}
        fields.update(created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
        if table.endswith("runs"):
            fields.update(service_date=date.today(), version=1)
        else:
            fields.update(sequence=1, status="partial")
        connection.execute(target.insert().values(**fields))
        with pytest.raises(RuntimeError, match="Dispatch records exist"):
            migration.downgrade()
        assert {"wholesale_dispatch_runs", "wholesale_dispatch_stops"} <= set(inspect(connection).get_table_names())
        assert connection.scalar(select(func.count()).select_from(target)) == 1


def test_postgresql_downgrade_locks_both_tables_before_checks_or_drops():
    from types import SimpleNamespace
    from unittest.mock import Mock
    path = Path(__file__).parents[1] / "migrations/versions/0084_wholesale_logistics.py"
    spec = importlib.util.spec_from_file_location("logistics_locking", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    calls = []
    connection = Mock(dialect=SimpleNamespace(name="postgresql"))
    def execute(statement):
        calls.append(str(statement))
        return Mock(first=lambda: None)
    connection.execute.side_effect = execute
    migration.op = Mock(get_bind=lambda: connection, drop_table=lambda table: calls.append("DROP " + table))
    migration.downgrade()
    assert calls[0] == "SET LOCAL lock_timeout = '5s'"
    assert calls[1] == "LOCK TABLE public.wholesale_dispatch_runs, public.wholesale_dispatch_stops IN ACCESS EXCLUSIVE MODE"
    assert "FROM wholesale_dispatch_runs" in calls[2]
    assert "FROM wholesale_dispatch_stops" in calls[3]
    assert calls[4:] == ["DROP wholesale_dispatch_stops", "DROP wholesale_dispatch_runs"]
    calls.clear()
    connection.execute.side_effect = RuntimeError("lock timeout")
    with pytest.raises(RuntimeError, match="lock timeout"):
        migration.downgrade()
    assert calls == []


def reconciliation_work(service, role="dev"):
    from backend.app.auth import RequestContext
    from backend.app.services.work import WorkService
    return WorkService(service.engine, RequestContext(service.actor, service.org, service.facility, role))


@pytest.mark.parametrize("outcome", ["partial", "rejected", "returned"])
def test_explicit_work_handoff_idempotency_route_and_isolation(setup, outcome):
    from modules.coman.models import WorkItem
    from backend.app.schemas.work import WorkUpdate
    engine, service, shipment, *_ = setup
    sh = shipment("WORK")
    rid = run(service)
    sid = add(service, rid, sh)
    arrived(engine, service, rid, sid, sh)
    status(service, rid, sid, "partial", recipient_name="Receiver", outcome_notes="Two refused")
    if outcome != "partial":
        # Separate rejection case does not change canonical shipment facts.
        if outcome == "rejected":
            with Session(engine) as session, session.begin():
                session.get(DispatchStop, sid).status = "rejected"
        else:
            status(service, rid, sid, "returned", outcome_notes="Returned for review")
    work = reconciliation_work(service)
    version = service.detail(rid)["version"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkItem)) == 0
        before_shipment = values(session.get(CommercialShipment, sh.id))
    first = service.create_reconciliation_work(rid, sid, version, work)
    retry = service.create_reconciliation_work(rid, sid, version, work)
    assert retry["work_item_id"] == first["work_item_id"]
    item = work.get(first["work_item_id"])
    assert (item["workspace"], item["entity_type"], item["entity_id"]) == ("Wholesale", "wholesale_dispatch_stop", sid)
    assert item["route"] == f"/wholesale?tab=fulfillment&dispatch={rid}&stop={sid}"
    work.update(item["id"], WorkUpdate(version=item["version"], status="completed"))
    assert service.detail(rid)["stops"][0]["status"] == outcome
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkItem)) == 1
        assert values(session.get(CommercialShipment, sh.id)) == before_shipment
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "dispatch_reconciliation_work_created")) == 1


def test_work_handoff_rollback_stale_removed_nonexception_and_scope(setup, monkeypatch):
    from modules.coman.models import WorkItem
    engine, service, shipment, other, *_ = setup
    rid = run(service)
    sh = shipment("ROLLBACK")
    sid = add(service, rid, sh)
    work = reconciliation_work(service)
    with pytest.raises(ValueError, match="exception"):
        service.create_reconciliation_work(rid, sid, 2, work)
    with pytest.raises(LookupError):
        service.create_reconciliation_work(rid, "removed", 2, work)
    arrived(engine, service, rid, sid, sh)
    status(service, rid, sid, "rejected", outcome_notes="Refused")
    with pytest.raises(ValueError, match="Refresh"):
        service.create_reconciliation_work(rid, sid, 1, work)
    foreign = LogisticsService(engine, service.org, other.id, service.actor)
    with pytest.raises(LookupError):
        foreign.create_reconciliation_work(rid, sid, 1, reconciliation_work(foreign))
    with pytest.raises(ValueError, match="context"):
        service.create_reconciliation_work(rid, sid, 1, reconciliation_work(foreign))
    version = service.detail(rid)["version"]
    def fail(*args):
        raise RuntimeError("audit unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(service, "_audit", fail)
        with pytest.raises(RuntimeError, match="audit unavailable"):
            service.create_reconciliation_work(rid, sid, version, work)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkItem)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_type == "work_item")) == 0
    detail = service.detail(rid)
    assert detail["version"] == version and detail["stops"][0]["work_item_id"] is None
    assert service.create_reconciliation_work(rid, sid, version, work)["work_item_id"]


@pytest.mark.parametrize("denied", ["work.create", "wholesale.manage_dispatch"])
def test_work_handoff_denied_override(setup, denied):
    from fastapi import HTTPException
    from modules.coman.permissions import AppUserPermissionOverride
    engine, service, shipment, *_ = setup
    rid = run(service)
    sh = shipment("DENIED")
    sid = add(service, rid, sh)
    arrived(engine, service, rid, sid, sh)
    status(service, rid, sid, "rejected", outcome_notes="Refused")
    with Session(engine) as session, session.begin():
        session.add(AppUserPermissionOverride(user_id=service.actor, organization_id=service.org,
            facility_id=service.facility, permission=denied, effect="deny", created_by="test", updated_by="test"))
    with pytest.raises(HTTPException) as error:
        service.create_reconciliation_work(rid, sid, service.detail(rid)["version"], reconciliation_work(service, "buyer"))
    assert error.value.status_code == 403
    assert service.detail(rid)["stops"][0]["work_item_id"] is None


def test_work_pointer_set_null_and_migration_chain(setup):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text
    from modules.coman.models import WorkItem
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_heads() == ["0085_cultivation_telemetry"]
    assert scripts.get_revision("0085_cultivation_telemetry").down_revision == "0084_wholesale_logistics"
    assert scripts.get_revision("0084_wholesale_logistics").down_revision == "0083_onboarding_reporting"
    engine, service, shipment, *_ = setup
    rid = run(service)
    sh = shipment("POINTER")
    sid = add(service, rid, sh)
    arrived(engine, service, rid, sid, sh)
    status(service, rid, sid, "rejected", outcome_notes="Refused")
    item = service.create_reconciliation_work(rid, sid, service.detail(rid)["version"], reconciliation_work(service))
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.commit()
        with connection.begin():
            connection.execute(WorkItem.__table__.delete().where(WorkItem.id == item["work_item_id"]))
    assert service.detail(rid)["stops"][0]["work_item_id"] is None
    fk = next(fk for fk in inspect(engine).get_foreign_keys("wholesale_dispatch_stops") if fk["constrained_columns"] == ["work_item_id"])
    assert fk["options"]["ondelete"] == "SET NULL"


def test_all_run_snapshots_optional(setup):
    _, service, *_ = setup
    result = service.create(RunInput(service_date=date.today()))
    for field in ("driver_name", "driver_license_number", "vehicle_license_plate_number", "vehicle_make", "vehicle_model"):
        assert result[field] is None
