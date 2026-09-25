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


def test_migration_roundtrip_and_evidence_preservation():
    migration = importlib.import_module("migrations.versions.0080_cultivation_telemetry")
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE cultivation_rooms (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36) NOT NULL, facility_id VARCHAR(36) NOT NULL)"))
        conn.execute(text("INSERT INTO cultivation_rooms VALUES ('r1','o1','f1')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            conn.execute(text("INSERT INTO cultivation_environment_targets VALUES ('t1','o1','f1','r1','temperature',20,25,60)"))
            with pytest.raises(RuntimeError, match="Preserve data"):
                migration.downgrade()
            conn.execute(text("DELETE FROM cultivation_environment_targets"))
            migration.downgrade()
            migration.upgrade()
        assert conn.execute(text("SELECT count(*) FROM cultivation_rooms")).scalar() == 1


def test_ui_api_routes_and_release_registration():
    root = Path(__file__).resolve().parents[1]
    assert "cultivation_telemetry_router" in (root / "backend/app/main.py").read_text()
    assert "CultivationEnvironmentPanel" in (root / "frontend/src/pages/CultivationOpsPage.tsx").read_text()
    assert "telemetry/rooms/" in (root / "frontend/src/components/CultivationEnvironmentPanel.tsx").read_text()
