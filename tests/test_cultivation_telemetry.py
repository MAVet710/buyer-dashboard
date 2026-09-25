from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import importlib
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext, get_request_context
from backend.app.database import get_engine
from backend.app.routers.cultivation_telemetry import router
from modules.coman.models import AuditEvent, Base, Facility, Organization
from modules.cultivation.models import CultivationRoom
from modules.cultivation.telemetry import Reading, TargetInput, TelemetryConflict, TelemetryService
from modules.cultivation.telemetry_models import EnvironmentalObservation as Observation

NOW = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all([Organization(id="o1", name="One", slug="one"), Organization(id="o2", name="Two", slug="two")])
        session.flush()
        session.add_all([Facility(id=f"f{i}", organization_id="o1" if i < 3 else "o2", name=f"F{i}", code=f"F{i}", cultivation_enabled=True) for i in (1, 2, 3)])
        session.flush()
        session.add_all([CultivationRoom(id=f"r{i}", organization_id="o1" if i < 3 else "o2", facility_id=f"f{i}", room_code="FLOWER") for i in (1, 2, 3)])
    yield engine, TelemetryService(engine)
    engine.dispose()


def reading(**kwargs):
    return {"source": "manual", "event_id": "event-1", "metric": "temperature", "value": 77, "unit": "F", "observed_at": NOW, **kwargs}


def ingest(service, rows, room="r1", facility="f1", org="o1"):
    return service.ingest(org, facility, room, rows, actor="tester")


def test_units_dedupe_conflicts_and_atomic_audit(setup):
    engine, service = setup
    assert ingest(service, [reading(), reading()]) == {"inserted": 1, "duplicates": 1}
    assert ingest(service, [reading(unit="C", value=25)]) == {"inserted": 0, "duplicates": 1}
    with pytest.raises(TelemetryConflict):
        ingest(service, [reading(event_id="new"), reading(value=90)])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Observation)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
    # Separate device, room, and source identities are preserved.
    assert ingest(service, [reading(device_id="probe-2"), reading(source="adapter-test")])["inserted"] == 2
    assert ingest(service, [reading()], room="r2", facility="f2")["inserted"] == 1


@pytest.mark.parametrize("org,facility,room", [("o2", "f1", "r1"), ("o1", "f2", "r1"), ("o1", "f1", "r3"), ("o1", "f1", "missing")])
def test_read_write_target_scope_fail_closed(setup, org, facility, room):
    _, service = setup
    with pytest.raises(LookupError):
        ingest(service, [reading()], room, facility, org)
    with pytest.raises(LookupError):
        service.snapshot(org, facility, room)
    with pytest.raises(LookupError):
        service.set_target(org, facility, room, {"metric": "temperature"}, actor="tester")


def test_database_rejects_cross_scope_room_reference(setup):
    engine, _ = setup
    with pytest.raises(IntegrityError), Session(engine) as session, session.begin():
        session.add(Observation(organization_id="o2", facility_id="f1", room_id="r1", **Reading(**reading()).model_dump()))


def test_concurrent_retries_insert_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'telemetry.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="o1", name="One", slug="one"))
        session.flush()
        session.add(Facility(id="f1", organization_id="o1", name="One", code="one"))
        session.flush()
        session.add(CultivationRoom(id="r1", organization_id="o1", facility_id="f1", room_code="one"))
    service = TelemetryService(engine)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: ingest(service, [reading()]), range(2)))
        assert sum(result["inserted"] for result in results) == 1
        assert sum(result["duplicates"] for result in results) == 1
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
    finally:
        engine.dispose()


def test_summaries_do_not_mix_facilities_or_organizations(setup):
    _, service = setup
    ingest(service, [reading(value=68)])
    ingest(service, [reading(value=86)], room="r2", facility="f2")
    ingest(service, [reading(value=104)], room="r3", facility="f3", org="o2")
    for org, facility, room, value in [("o1", "f1", "r1", 20), ("o1", "f2", "r2", 30), ("o2", "f3", "r3", 40)]:
        snapshot = service.snapshot(org, facility, room, now=NOW)
        row = next(r for r in snapshot["readings"] if r["metric"] == "temperature")
        assert row["value"] == value
        assert row["trend_24h"]["count"] == 1


@pytest.mark.parametrize("changes", [
    {"unit": "K"}, {"value": float("nan")}, {"value": float("inf")},
    {"observed_at": NOW.replace(tzinfo=None)}, {"observed_at": datetime.now(timezone.utc) + timedelta(days=1)},
    {"metric": "relative_humidity", "unit": "%", "value": 101},
    {"metric": "substrate_vwc", "unit": "%", "value": -1},
    {"metric": "irrigation_event", "unit": "count", "value": 2},
    {"source": " "}, {"quality": "excellent"}, {"organization_id": "o2"},
])
def test_invalid_evidence_is_rejected(changes):
    with pytest.raises(ValidationError):
        Reading(**reading(**changes))


@pytest.mark.parametrize("metric,value,unit,expected", [
    ("temperature", 77, "F", 25), ("relative_humidity", 55, "%", 55),
    ("substrate_ec", 2200, "uS/cm", 2.2), ("substrate_vwc", 35, "%", 35),
    ("irrigation_volume", 1500, "mL", 1.5), ("irrigation_event", 1, "count", 1),
    ("co2", 1000, "ppm", 1000), ("vpd", 1.2, "kPa", 1.2),
])
def test_canonical_units(metric, value, unit, expected):
    assert Reading(**reading(metric=metric, value=value, unit=unit)).value == expected


def test_stale_range_quality_missing_trends_and_out_of_order(setup):
    _, service = setup
    service.set_target("o1", "f1", "r1", {"metric": "temperature", "minimum": 20, "maximum": 24, "stale_minutes": 30}, actor="tester")
    service.set_target("o1", "f1", "r1", {"metric": "co2", "stale_minutes": 60}, actor="tester")
    ingest(service, [reading(), reading(event_id="older", observed_at=NOW - timedelta(hours=1), value=68),
        reading(event_id="bad", device_id="bad-probe", quality="invalid", value=200),
        reading(event_id="event", metric="irrigation_event", value=1, unit="count", observed_at=NOW - timedelta(days=2))])
    snapshot = service.snapshot("o1", "f1", "r1", now=NOW + timedelta(minutes=31))
    row = next(r for r in snapshot["readings"] if r["metric"] == "temperature" and not r["device_id"])
    assert row["states"] == ["stale", "out_of_range"]
    assert row["value"] == 25
    assert row["trend_24h"]["average"] == 22.5
    assert row["trend_24h"]["count"] == 2
    bad = next(r for r in snapshot["readings"] if r["device_id"] == "bad-probe")
    assert bad["states"] == ["stale", "invalid"]
    assert bad["trend_24h"] is None
    assert next(r for r in snapshot["readings"] if r["metric"] == "irrigation_event")["states"] == ["current"]
    assert next(r for r in snapshot["exceptions"] if r["metric"] == "co2")["states"] == ["missing"]
    assert not any(r["metric"] == "relative_humidity" for r in snapshot["exceptions"])
    assert snapshot["decision_support_only"] is True


def test_range_edges_and_stale_boundary(setup):
    _, service = setup
    service.set_target("o1", "f1", "r1", TargetInput(metric="temperature", minimum=25, maximum=25), actor="tester")
    ingest(service, [reading()])
    assert service.snapshot("o1", "f1", "r1", now=NOW + timedelta(minutes=60))["exceptions"] == []
    with pytest.raises(ValidationError):
        TargetInput(metric="temperature", minimum=30, maximum=20)


def test_summary_is_bounded_and_query_count_constant(setup):
    engine, service = setup
    ingest(service, [reading(device_id=f"probe-{i:03}") for i in range(205)])
    statements = []
    def capture(*args):
        statements.append(args[2])
    event.listen(engine, "before_cursor_execute", capture)
    try:
        snapshot = service.snapshot("o1", "f1", "r1", now=NOW)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert snapshot["truncated"] is True
    assert len(snapshot["readings"]) == 200
    assert len(statements) == 4
    assert all(row["trend_24h"]["count"] == 1 for row in snapshot["readings"])
    assert "LIMIT" in statements[2].upper()
    assert "GROUP BY" in statements[3].upper() and "LIMIT" in statements[3].upper()
    assert " IN " in statements[3].upper()  # Only the selected bounded streams are aggregated.


def test_api_contract_scope_roles_and_conflict(setup):
    engine, _ = setup
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    context = RequestContext("tester", "o1", "f1", "operator")
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    path = "/api/v1/inventory/production/plants/telemetry/rooms/r1"
    body = {"observations": [reading(observed_at=NOW.isoformat())]}
    assert client.post(path + "/observations", json=body).json() == {"inserted": 1, "duplicates": 0}
    assert client.post(path + "/observations", json=body).json()["duplicates"] == 1
    body["observations"][0]["value"] = 90
    assert client.post(path + "/observations", json=body).status_code == 409
    result = client.get(path)
    assert result.status_code == 200
    assert {"readings", "exceptions", "as_of", "truncated", "room_id", "decision_support_only"} <= result.json().keys()
    assert client.get(path.replace("r1", "r2")).status_code == 404
    context = RequestContext("tester", "o1", "f1", "viewer")
    assert client.get(path).status_code == 200
    assert client.post(path + "/observations", json=body).status_code == 403
    assert client.post(path + "/target", json={"metric": "temperature"}).status_code == 403
    context = RequestContext("tester", "o1", "f1", "operator")
    with Session(engine) as session, session.begin():
        session.get(Facility, "f1").cultivation_enabled = False
    assert client.get(path).status_code == 403


@pytest.mark.parametrize("populated", ["targets", "observations"])
def test_migration_roundtrip_and_evidence_preservation(populated):
    migration = importlib.import_module("migrations.versions.0080_cultivation_telemetry")
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE cultivation_rooms (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36) NOT NULL, facility_id VARCHAR(36) NOT NULL)"))
        conn.execute(text("INSERT INTO cultivation_rooms VALUES ('r1','o1','f1')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            if populated == "targets":
                conn.execute(text("INSERT INTO cultivation_environment_targets VALUES ('t1','o1','f1','r1','temperature',20,25,60)"))
            else:
                conn.execute(text("INSERT INTO cultivation_environment_observations VALUES ('e1','o1','f1','r1','temperature','manual','event','','25','C','valid','2026-01-02','2026-01-02')"))
            with pytest.raises(RuntimeError, match="Preserve data"):
                migration.downgrade()
            assert conn.execute(text(f"SELECT count(*) FROM cultivation_environment_{populated}")).scalar() == 1
            conn.execute(text(f"DELETE FROM cultivation_environment_{populated}"))
            migration.downgrade()
            migration.upgrade()
        assert conn.execute(text("SELECT count(*) FROM cultivation_rooms")).scalar() == 1


def test_ui_api_routes_and_release_registration():
    root = Path(__file__).resolve().parents[1]
    assert "cultivation_telemetry_router" in (root / "backend/app/main.py").read_text()
    assert "CultivationEnvironmentPanel" in (root / "frontend/src/pages/CultivationOpsPage.tsx").read_text()
    assert "telemetry/rooms/" in (root / "frontend/src/components/CultivationEnvironmentPanel.tsx").read_text()


@pytest.mark.parametrize("value", [25, 35])
@pytest.mark.parametrize("quality,age,expected", [
    ("valid", 0, ["current"]), ("valid", 61, ["stale"]),
    ("suspect", 0, ["suspect"]), ("invalid", 0, ["invalid"]),
    ("suspect", 61, ["stale", "suspect"]), ("invalid", 61, ["stale", "invalid"]),
])
def test_targets_never_suppress_quality_or_staleness(setup, quality, age, expected, value):
    _, service = setup
    service.set_target("o1", "f1", "r1", {"metric": "temperature", "minimum": 20, "maximum": 30}, actor="tester")
    ingest(service, [reading(quality=quality, unit="C", value=value)])
    row = service.snapshot("o1", "f1", "r1", now=NOW + timedelta(minutes=age))["readings"][0]
    if quality == "valid" and value > 30:
        expected = (["stale"] if age > 60 else []) + ["out_of_range"]
    assert row["states"] == expected
    if quality != "valid":
        assert row["trend_24h"] is None


def test_irrigation_totals_use_valid_discrete_events_in_exact_window(setup):
    _, service = setup
    rows = []
    for metric, unit, value in [("irrigation_event", "count", 1), ("irrigation_volume", "mL", 1500)]:
        for event_id, quality, age in [("a", "valid", 0), ("b", "valid", 1), ("c", "invalid", 2),
                                       ("d", "suspect", 3), ("boundary", "valid", 24)]:
            rows.append(reading(metric=metric, unit=unit, value=value, event_id=event_id,
                                quality=quality, observed_at=NOW - timedelta(hours=age)))
    ingest(service, rows)
    snapshot = service.snapshot("o1", "f1", "r1", now=NOW)
    trends = {row["metric"]: row["trend_24h"] for row in snapshot["readings"]}
    assert trends["irrigation_event"] == {"kind": "event_count", "count": 2, "total": 2}
    assert trends["irrigation_volume"] == {"kind": "volume_total", "count": 2, "total": 3}
    later = service.snapshot("o1", "f1", "r1", now=NOW + timedelta(days=2))
    assert all(row["trend_24h"] is None for row in later["readings"])


def test_exception_identity_and_explicit_work_draft_are_read_only(setup):
    engine, service = setup
    ingest(service, [reading(quality="suspect"), reading(quality="suspect", device_id="second"),
                     reading(quality="suspect", source="other")])
    first = service.snapshot("o1", "f1", "r1", now=NOW)["exceptions"]
    second = service.snapshot("o1", "f1", "r1", now=NOW + timedelta(minutes=1))["exceptions"]
    assert [r["exception_id"] for r in first] == [r["exception_id"] for r in second]
    assert len({r["exception_id"] for r in first}) == 3
    selected = next(r for r in first if r["source"] == "manual" and not r["device_id"])
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(AuditEvent))
    draft = service.prepare_work_item("o1", "f1", "r1", selected["exception_id"], actor="tester", now=NOW)
    assert draft["origin_id"] == selected["exception_id"]
    assert draft["evidence"] == selected
    assert draft["requested_by"] == "tester"
    assert draft["room_id"] == "r1"
    assert draft["decision_support_only"] is True
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    with pytest.raises(LookupError):
        service.prepare_work_item("o2", "f1", "r1", selected["exception_id"], actor="tester", now=NOW)
    with pytest.raises(TelemetryConflict):
        service.prepare_work_item("o1", "f2", "r2", selected["exception_id"], actor="tester", now=NOW)
    with pytest.raises(ValueError):
        service.prepare_work_item("o1", "f1", "r1", selected["exception_id"], actor="", now=NOW)
    ingest(service, [reading(event_id="replacement", observed_at=NOW + timedelta(minutes=1))])
    with pytest.raises(TelemetryConflict):
        service.prepare_work_item("o1", "f1", "r1", selected["exception_id"], actor="tester", now=NOW + timedelta(minutes=1))


def test_missing_and_state_transition_identity(setup):
    _, service = setup
    for room, facility in [("r1", "f1"), ("r2", "f2")]:
        service.set_target("o1", facility, room, {"metric": "temperature"}, actor="tester")
    missing = service.snapshot("o1", "f1", "r1", now=NOW)["exceptions"][0]["exception_id"]
    assert missing == service.snapshot("o1", "f1", "r1", now=NOW + timedelta(hours=1))["exceptions"][0]["exception_id"]
    assert missing != service.snapshot("o1", "f2", "r2", now=NOW)["exceptions"][0]["exception_id"]
    ingest(service, [reading(quality="invalid")])
    fresh = service.snapshot("o1", "f1", "r1", now=NOW)["exceptions"][0]["exception_id"]
    stale = service.snapshot("o1", "f1", "r1", now=NOW + timedelta(hours=2))["exceptions"][0]["exception_id"]
    assert len({missing, fresh, stale}) == 3


def test_equal_timestamp_latest_is_independent_of_delivery_order(setup):
    _, service = setup
    ingest(service, [reading(event_id="z", quality="invalid")])
    ingest(service, [reading(event_id="a")])
    row = service.snapshot("o1", "f1", "r1", now=NOW)["exceptions"][0]
    assert row["event_id"] == "z"
    assert row["states"] == ["invalid"]


@pytest.mark.parametrize("role,allowed", [("dev", True), ("admin", True), ("supervisor", True),
    ("operator", True), ("qa", True), ("buyer", False), ("planner", False), ("viewer", False),
    ("read_only", False), ("trial", False), ("user", False), ("unknown", False)])
def test_write_authorization_hook_retains_role_and_capability_gates(setup, role, allowed):
    from backend.app.routers.cultivation_telemetry import authorize_telemetry
    from fastapi import HTTPException
    engine, _ = setup
    context = RequestContext("tester", "o1", "f1", role)
    if allowed:
        authorize_telemetry(context, engine, write=True)
    else:
        with pytest.raises(HTTPException) as error:
            authorize_telemetry(context, engine, write=True)
        assert error.value.status_code == 403
    with Session(engine) as session, session.begin():
        session.get(Facility, "f1").cultivation_enabled = False
    with pytest.raises(HTTPException) as error:
        authorize_telemetry(context, engine, write=True)
    assert error.value.status_code == 403


def test_postgresql_acl_contract(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    migration = importlib.import_module("migrations.versions.0080_cultivation_telemetry")
    statements = []
    @contextmanager
    def batch(*args):
        yield SimpleNamespace(create_unique_constraint=lambda *args: None)
    monkeypatch.setattr(migration, "op", SimpleNamespace(batch_alter_table=batch,
        create_table=lambda *args: None, create_index=lambda *args: None,
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")), execute=statements.append))
    migration.upgrade()
    sql = "\n".join(statements)
    for table in migration.TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM %I" in sql
    assert "ARRAY['anon','authenticated']" in sql
    assert "GRANT SELECT, INSERT ON TABLE public.cultivation_environment_observations TO doobielogic_render_runtime" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE public.cultivation_environment_targets TO doobielogic_render_runtime" in sql
    assert "CREATE POLICY" not in sql


def test_telemetry_exposes_no_provider_or_equipment_path():
    import ast
    root = Path(__file__).resolve().parents[1]
    for path in ["modules/cultivation/telemetry.py", "backend/app/routers/cultivation_telemetry.py"]:
        tree = ast.parse((root / path).read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        assert not any(any(name in module for name in ("requests", "httpx", "socket", "subprocess", "trolmaster", "growlink", "argus")) for module in imports)
    assert {(route.path, tuple(sorted(route.methods))) for route in router.routes} == {
        ("/inventory/production/plants/telemetry/rooms/{room_id}", ("GET",)),
        ("/inventory/production/plants/telemetry/rooms/{room_id}/target", ("POST",)),
        ("/inventory/production/plants/telemetry/rooms/{room_id}/observations", ("POST",)),
    }
    for field in ("credentials", "equipment_command", "irrigation_command", "vendor_api_key"):
        with pytest.raises(ValidationError):
            Reading(**reading(**{field: "not-accepted"}))
