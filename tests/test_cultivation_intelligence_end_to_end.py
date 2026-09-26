"""Independent HTTP acceptance. Only context, settings and database are substituted.

Missing promised routes are failures, never skips or successful 503 assertions.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["COMAN_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AI_ALLOW_CLOUD_FALLBACK"] = "false"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app import config
from backend.app.auth import RequestContext, get_request_context
from backend.app.database import get_engine
from backend.app.routers import cultivation_intelligence_workspace as workspace
from backend.app.routers import cultivation_telemetry as legacy
from modules.coman.models import AppUser, Base, Facility, Organization
from modules.cultivation.edge_store import EdgeStore, Scope
from modules.cultivation.models import CultivationPlant, CultivationRoom, CultivationHarvestPlant
from modules.cultivation.intelligence_models import CultivationHarvest
from modules.cultivation.telemetry_models import EnvironmentalObservation

PREFIX = "/api/v1/cultivation-intelligence"


def seed_scope(engine):
    with Session(engine) as s, s.begin():
        org = Organization(name="Acceptance", slug=str(uuid4()))
        s.add(org)
        s.flush()
        facility = Facility(organization_id=org.id, name="Acceptance", code=str(uuid4()), cultivation_enabled=True)
        user = AppUser(organization_id=org.id, username=str(uuid4()), normalized_username=str(uuid4()), password_hash="unusable-test-only", role="admin")
        s.add_all([facility, user])
        s.flush()
        room = CultivationRoom(organization_id=org.id, facility_id=facility.id, room_code="FLOWER-A", display_name="Flower A", phase="flowering")
        plant = CultivationPlant(organization_id=org.id, facility_id=facility.id, plant_tag=str(uuid4()), strain_name="Fixture", phase="flowering", room_code="FLOWER-A")
        harvest = CultivationHarvest(organization_id=org.id, facility_id=facility.id, harvest_code=str(uuid4()), strain="Fixture", created_by=user.id, harvested_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
        s.add_all([room, plant, harvest])
        s.flush()
        s.add(CultivationHarvestPlant(organization_id=org.id, facility_id=facility.id, harvest_id=harvest.id, plant_id=plant.id, assigned_by=user.id))
        return SimpleNamespace(org=org.id, facility=facility.id, user=user.id, room=room.id, plant=plant.id, harvest=harvest.id)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    engine = create_engine("sqlite+pysqlite:///" + (tmp_path / "central.db").as_posix(), connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    mutations = []
    @event.listens_for(engine, "before_cursor_execute")
    def record_mutations(conn, cursor, statement, parameters, context, executemany):
        match = re.match(r'\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+["`]?([a-zA-Z0-9_]+)', statement, re.I)
        if match:
            mutations.append(match.group(1))
    own, other = seed_scope(engine), seed_scope(engine)
    edge = EdgeStore(tmp_path / "edge.db")
    monkeypatch.setenv("CULTIVATION_EDGE_PATH", str(edge.path))
    settings = config.Settings(_env_file=None, app_env="test", database_url=str(engine.url), cultivation_edge_path=str(edge.path))
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    # Replace any already-imported settings dependency, never a domain service.
    for module in (workspace,):
        if hasattr(module, "get_settings"):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(workspace.router, prefix="/api/v1")
    app.include_router(legacy.router, prefix="/api/v1")
    state = {"context": RequestContext(user_id=own.user, organization_id=own.org, facility_id=own.facility, role="admin")}
    app.dependency_overrides[get_request_context] = lambda: state["context"]
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[config.get_settings] = lambda: settings
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, engine=engine, own=own, other=other, edge=edge, state=state, mutations=mutations)
    engine.dispose()


def post(h, path, body, status=200):
    response = h.client.post(PREFIX + path, json=body)
    assert response.status_code == status, f"POST {path}: {response.status_code} {response.text}"
    return response.json()


def get(h, path):
    response = h.client.get(PREFIX + path)
    assert response.status_code == 200, f"GET {path}: {response.status_code} {response.text}"
    return response.json()


def test_relationships_approval_versions_scope_and_canonical_harvest(harness):
    h = harness
    recipe = post(h, "/recipes", {"name": "Approved fixture", "stages": [{"stage_key": "facility-flower", "display_name": "Facility Flower", "sequence": 1, "targets": [{"metric": "temperature", "minimum": 20, "maximum": 24, "unit": "C"}]}]})
    post(h, "/cycles", {"cycle_code": "unapproved", "display_name": "Rejected", "recipe_id": recipe["id"]}, 422)
    approved = post(h, f'/recipes/{recipe["id"]}/approve', {"version": recipe["version"]})
    assert approved["approved_by"] == h.own.user
    post(h, f'/recipes/{recipe["id"]}/approve', {"version": recipe["version"]}, 409)
    cycle = post(h, "/cycles", {"cycle_code": "cycle", "display_name": "Fixture", "recipe_id": recipe["id"]})
    occupancy = {"version": cycle["version"], "room_id": h.own.room, "stage_id": recipe["stages"][0]["id"], "entered_at": "2026-09-01T00:00:00Z"}
    post(h, f'/cycles/{cycle["id"]}/occupancy', dict(occupancy, room_id=h.other.room), 404)
    moved = post(h, f'/cycles/{cycle["id"]}/occupancy', occupancy)
    post(h, f'/cycles/{cycle["id"]}/occupancy', occupancy, 409)
    joined = post(h, f'/cycles/{cycle["id"]}/members', {"version": moved["version"], "plant_ids": [h.own.plant], "action": "add", "effective_at": "2026-09-01T00:00:00Z"})
    post(h, f'/cycles/{cycle["id"]}/harvest', {"version": joined["version"], "harvest_id": h.own.harvest})
    detail = get(h, f'/cycles/{cycle["id"]}')
    assert detail["members"][0]["plant_id"] == h.own.plant
    assert detail["harvest"]["id"] == h.own.harvest
    assert detail["occupancy"][0]["stage_id"] == recipe["stages"][0]["id"]
    assert detail["economics"]["allocated_cost"] is None
    assert get(h, f"/plants/{h.own.plant}/exposure")["exposure_status"] == "unknown"
    assert h.client.get(PREFIX + f"/rooms/{h.other.room}").status_code == 404
    h.state["context"] = RequestContext(user_id=h.own.user, organization_id=h.own.org, facility_id=h.own.facility, role="read_only")
    assert get(h, "/workspace")["can_manage"] is False
    post(h, "/cycles", {"cycle_code": "readonly", "display_name": "Rejected"}, 403)
    post(h, "/connections", {"provider": "json", "label": "Rejected"}, 403)


def test_connection_non_live_revoke_and_versions(harness):
    h = harness
    connection = post(h, "/connections", {"provider": "growlink", "label": "File fixture", "mode": "file"})
    assert connection["live_supported"] is False
    assert connection["status"] == "configured"
    device = post(h, f'/connections/{connection["id"]}/devices', {"version": connection["version"], "source_device_id": "fixture"})
    post(h, f'/connections/{connection["id"]}/revoke', {"version": connection["version"]}, 409)
    current = get(h, "/connections")["connections"][0]
    revoked = post(h, f'/connections/{connection["id"]}/revoke', {"version": current["version"]})
    assert revoked["revoked_at"] and revoked["status"] == "revoked"
    post(h, f'/connections/{connection["id"]}/devices', {"version": revoked["version"], "source_device_id": "blocked"}, 409)
    post(h, f'/devices/{device["id"]}/sensors', {"version": device["version"], "source_channel": "temp", "source_metric": "vendor_temp", "source_unit": "F", "metric": "temperature"}, 409)


def test_legacy_http_preserves_original_units_and_exact_replay(harness):
    h = harness
    path = f"/api/v1/inventory/production/plants/telemetry/rooms/{h.own.room}/observations"
    body = {"observations": [{"source": "manual", "event_id": "fahrenheit", "device_id": "fixture", "metric": "temperature", "value": 77, "unit": "F", "observed_at": "2026-09-01T00:00:00Z"}]}
    for _ in range(2):
        response = h.client.post(path, json=body)
        assert response.status_code == 200, response.text
    with Session(h.engine) as s:
        rows = s.scalars(select(EnvironmentalObservation)).all()
        assert len(rows) == 1
        row = rows[0]
        assert (row.value, row.unit) == (25, "C")
        assert (row.original_value, row.original_unit, row.source_metric) == (77, "F", "temperature")


@pytest.mark.parametrize("method,suffix", [("post", "/imports/preview"), ("post", "/imports"), ("post", "/drain"), ("get", "/health")])
def test_promised_gateway_routes_are_registered(harness, method, suffix):
    routes = {(verb, path) for path, verbs in harness.client.app.openapi()["paths"].items() for verb in verbs}
    assert (method, PREFIX + "/connections/{identity}" + suffix) in routes, f"Promised {method.upper()} {suffix} is absent"


def test_raw_fixture_preview_import_replay_and_local_evidence(harness):
    """Real gateway acceptance, intentionally fails until the promised seam exists."""
    h = harness
    connection = post(h, "/connections", {"provider": "json", "label": "Raw fixture"})
    scope = Scope(h.own.org, h.own.facility, connection["id"])
    content = json.dumps([{"event_id": "raw-1", "source_device_id": "fixture", "source_channel": "temp", "source_metric": "vendor_temp", "value": 77, "unit": "F", "observed_at": "2026-09-01T00:00:00Z"}])
    body = {"format": "json", "content": content, "mappings": [{"source_channel": "temp", "source_metric": "vendor_temp", "metric": "temperature", "unit": "F"}]}
    before = table_counts(h.engine)
    preview = post(h, f'/connections/{connection["id"]}/imports/preview', body)
    assert preview["rows"] == 1
    assert h.edge.evidence(scope)["items"] == []
    assert table_counts(h.engine) == before, "Preview must not persist central state"
    committed = post(h, f'/connections/{connection["id"]}/imports', dict(body, digest=preview["digest"]))
    assert committed["accepted"] == 0 and committed["queued_for_mapping"] == 1
    replay = post(h, f'/connections/{connection["id"]}/imports', dict(body, digest=preview["digest"]))
    assert replay["duplicates"] == 1 and replay["accepted"] == 0
    items = h.edge.evidence(scope)["items"]
    assert len(items) == 1
    assert items[0]["raw"]["value"] == 77 and items[0]["raw"]["unit"] == "F"
    after = table_counts(h.engine)
    # Import may add audit evidence only. No per-sample central observations,
    # auto Work, equipment, inventory, plant, or traceability writes are allowed.
    assert {k: v for k, v in after.items() if k != "coman_audit_events"} == {k: v for k, v in before.items() if k != "coman_audit_events"}
    health = get(h, f'/connections/{connection["id"]}/health')
    assert health["live_contract_status"] == "blocked"
    assert health["connection"]["live_supported"] is False
    original_context = h.state["context"]
    h.state["context"] = RequestContext(user_id=h.other.user, organization_id=h.other.org, facility_id=h.other.facility, role="admin")
    post(h, f'/connections/{connection["id"]}/imports', dict(body, digest=preview["digest"]), 404)
    assert h.client.get(PREFIX + f'/connections/{connection["id"]}/health').status_code == 404
    h.state["context"] = RequestContext(user_id=h.own.user, organization_id=h.own.org, facility_id=h.own.facility, role="read_only")
    post(h, f'/connections/{connection["id"]}/imports', dict(body, digest=preview["digest"]), 403)
    post(h, f'/connections/{connection["id"]}/drain', {"limit": 100}, 403)
    h.state["context"] = original_context
    post(h, f'/connections/{connection["id"]}/revoke', {"version": connection["version"]})
    post(h, f'/connections/{connection["id"]}/imports', dict(body, digest=preview["digest"]), 409)
    assert len(h.edge.evidence(scope)["items"]) == 1


def table_counts(engine):
    with engine.connect() as connection:
        return {table.name: connection.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables}


@pytest.fixture
def historical_context(harness):
    """Persist historical setup, not fake resolver output or a substituted clock.

    Past approved recipes/mappings are pre-existing database fixtures because the
    HTTP mapping API accepts only future revisions. HTTP approval is tested above.
    All attribution, import, replay and rollups below run the real implementation.
    """
    from modules.cultivation.intelligence_models import (
        CultivationRecipe, CultivationRecipeStage, CultivationRecipeTarget,
        CropCycle, CropCycleRoom, CropCyclePlant, DeviceMapping,
    )
    h = harness
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    connection = post(h, "/connections", {"provider": "growlink", "label": "Historical file"})
    device = post(h, f'/connections/{connection["id"]}/devices', {"version": connection["version"], "source_device_id": "fixture"})
    sensor = post(h, f'/devices/{device["id"]}/sensors', {"version": device["version"], "source_channel": "temp", "source_metric": "vendor_temp", "source_unit": "F", "metric": "temperature"})
    values = {"organization_id": h.own.org, "facility_id": h.own.facility}
    with Session(h.engine) as s, s.begin():
        recipe = CultivationRecipe(**values, name="Historical approved", version=1, created_by=h.own.user, status="approved", approved_by=h.own.user, approved_at=start-timedelta(days=1))
        s.add(recipe)
        s.flush()
        stage = CultivationRecipeStage(**values, recipe_id=recipe.id, stage_key="facility-flower", display_name="Facility flower", sequence=1)
        cycle = CropCycle(**values, cycle_code="historical", display_name="Historical crop", recipe_id=recipe.id, created_by=h.own.user, status="active")
        s.add_all([stage, cycle])
        s.flush()
        mapping = DeviceMapping(**values, device_id=device["id"], room_id=h.own.room, effective_at=start-timedelta(days=1), created_by=h.own.user)
        s.add_all([
            mapping,
            CultivationRecipeTarget(**values, stage_id=stage.id, metric="temperature", minimum=20, maximum=24, unit="C"),
            CropCycleRoom(**values, cycle_id=cycle.id, room_id=h.own.room, stage_id=stage.id, entered_at=start-timedelta(days=1), assigned_by=h.own.user),
            CropCyclePlant(**values, cycle_id=cycle.id, plant_id=h.own.plant, added_at=start-timedelta(days=1), added_by=h.own.user),
        ])
        s.flush()
        h.history = SimpleNamespace(connection=connection["id"], device=device["id"], device_version=sensor["version"], sensor=sensor["id"], mapping=mapping.id, recipe=recipe.id, stage=stage.id, cycle=cycle.id, start=start, end=end)
    return h


def import_historical(h):
    x = h.history
    rows = [
        {"event_id": "known", "source_device_id": "fixture", "source_channel": "temp", "source_metric": "vendor_temp", "value": 77, "unit": "F", "observed_at": x.start.isoformat()},
        {"event_id": "unknown", "source_device_id": "unregistered", "source_channel": "temp", "source_metric": "vendor_temp", "value": 80, "unit": "F", "observed_at": x.start.isoformat()},
    ]
    body = {"format": "json", "content": json.dumps(rows), "mappings": [{"source_channel": "temp", "source_metric": "vendor_temp", "metric": "temperature", "unit": "F"}]}
    before = table_counts(h.engine)
    mutation_start = len(h.mutations)
    preview = post(h, f"/connections/{x.connection}/imports/preview", body)
    assert preview["rows"] == 2 and preview["unknown_channels"] == [1]
    assert preview["can_commit"] is True and preview["conflicts"] == []
    assert table_counts(h.engine) == before
    scope = Scope(h.own.org, h.own.facility, x.connection)
    assert h.edge.evidence(scope)["items"] == []
    body["digest"] = preview["digest"]
    x.import_body = body
    result = post(h, f"/connections/{x.connection}/imports", body)
    assert result["accepted"] == 1 and result["queued_for_mapping"] == 1
    replay = post(h, f"/connections/{x.connection}/imports", body)
    assert replay["accepted"] == 0 and replay["duplicates"] == 2
    drained = post(h, f"/connections/{x.connection}/drain", {"limit": 100})
    assert drained["pending"] == 1
    evidence = h.edge.evidence(scope)["items"]
    assert len(evidence) == 2
    ready = next(row for row in evidence if row["state"] == "ready")
    assert ready["raw"]["value"] == 77 and ready["raw"]["unit"] == "F"
    assert ready["canonical"]["value"] == 25
    snap = ready["snapshot"]
    assert (snap["room_id"], snap["cycle_id"], snap["stage_id"], snap["recipe_revision"]) == (h.own.room, x.cycle, x.stage, x.recipe)
    assert (snap["mapping_revision"], snap["sensor_id"]) == (x.mapping, x.sensor)
    assert (snap["target_min"], snap["target_max"]) == (20, 24)
    summary = h.edge.room_summary(h.own.org, h.own.facility, h.own.room, x.start, x.end, cycle_id=x.cycle)
    stream = summary["streams"][0]
    assert stream["sample_mean"] == 25
    assert stream["coverage_seconds"] == 300 and stream["unknown_seconds"] == 3300
    assert stream["above_seconds"] == 300 and stream["status"] == "PARTIAL"
    assert h.edge.room_summary(h.other.org, h.other.facility, h.own.room, x.start, x.end)["streams"] == []
    after = table_counts(h.engine)
    assert set(h.mutations[mutation_start:]) <= {"coman_audit_events"}, "Gateway may write count-only audit evidence, never central per-sample or operational state"
    assert {k: v for k, v in after.items() if k != "coman_audit_events"} == {k: v for k, v in before.items() if k != "coman_audit_events"}
    return stream


def test_actual_gateway_attribution_rollup_room360_and_gap(historical_context):
    h = historical_context
    empty = get(h, f"/rooms/{h.own.room}")
    assert empty["edge_summary"]["status"] == "UNKNOWN"
    assert empty["edge_summary"]["streams"] == []
    import_historical(h)
    post(h, f'/devices/{h.history.device}/mapping', {"version": h.history.device_version, "room_id": h.own.room, "effective_at": (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
    path = f'/connections/{h.history.connection}'
    post(h, path + '/imports', h.history.import_body, 409)
    preview_body = {k: v for k, v in h.history.import_body.items() if k != 'digest'}
    preview = post(h, path + '/imports/preview', preview_body)
    replay = post(h, path + '/imports', dict(preview_body, digest=preview['digest']))
    assert replay["duplicates"] == 2 and replay["accepted"] == 0
    evidence = h.edge.evidence(Scope(h.own.org, h.own.facility, h.history.connection))["items"]
    assert next(row for row in evidence if row["state"] == "ready")["snapshot"]["mapping_revision"] == h.history.mapping
    room = get(h, f"/rooms/{h.own.room}")
    stream = room["edge_summary"]["streams"][0]
    assert stream["snapshot"]["cycle_id"] == h.history.cycle
    assert stream["sample_mean"] == 25 and stream["coverage_seconds"] == 300
    assert stream["unknown_seconds"] == 86400 - 300
    health = get(h, f"/connections/{h.history.connection}/health")
    assert health["live_contract_status"] == "blocked"
    assert health["connection"]["status"] == "configured"
    assert health["connection"]["live_supported"] is False


def test_cycle360_returns_attributed_rollup_evidence(historical_context):
    h = historical_context
    import_historical(h)
    detail = get(h, f"/cycles/{h.history.cycle}")
    assert "edge_summary" in detail, "Cycle360 lacks the promised attributed rollup evidence"
    rooms = detail['edge_summary']['rooms']
    assert len(rooms) == 1 and rooms[0]['room_id'] == h.own.room
    streams = rooms[0]['summary']['streams']
    assert streams and detail['edge_summary']['truncated'] is False
    assert any(obj["snapshot"]["cycle_id"] == h.history.cycle and obj["sample_mean"] == 25 and obj["coverage_seconds"] == 300 for obj in streams)


def test_effective_mapping_http_version_scope_and_unknown_before_effective(harness):
    h = harness
    connection = post(h, "/connections", {"provider": "json", "label": "Mapping fixture"})
    device = post(h, f'/connections/{connection["id"]}/devices', {"version": connection["version"], "source_device_id": "fixture"})
    body = {"version": device["version"], "room_id": h.own.room, "effective_at": (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
    post(h, f'/devices/{device["id"]}/mapping', dict(body, room_id=h.other.room), 404)
    mapped = post(h, f'/devices/{device["id"]}/mapping', body)
    assert mapped["version"] == device["version"] + 1
    post(h, f'/devices/{device["id"]}/mapping', body, 409)
    post(h, f'/devices/{device["id"]}/sensors', {"version": mapped["version"], "source_channel": "temp", "source_metric": "vendor_temp", "source_unit": "F", "metric": "temperature"})
    raw = {"format": "json", "content": json.dumps([{"event_id": "early", "source_device_id": "fixture", "source_channel": "temp", "source_metric": "vendor_temp", "value": 77, "unit": "F", "observed_at": "2026-09-01T00:00:00Z"}]), "mappings": [{"source_channel": "temp", "source_metric": "vendor_temp", "metric": "temperature", "unit": "F"}]}
    preview = post(h, f'/connections/{connection["id"]}/imports/preview', raw)
    assert preview["unknown_channels"] == [0]
    result = post(h, f'/connections/{connection["id"]}/imports', dict(raw, digest=preview["digest"]))
    assert result["queued_for_mapping"] == 1
    item = h.edge.evidence(Scope(h.own.org, h.own.facility, connection["id"]))["items"][0]
    assert item["snapshot"] is None


def test_import_digest_is_bound_to_connection_version(harness):
    h = harness
    connection = post(h, "/connections", {"provider": "json", "label": "Version-bound import"})
    path = f'/connections/{connection["id"]}'
    body = {"format": "json", "content": "[]", "mappings": []}
    preview = post(h, path + "/imports/preview", body)
    post(h, path + "/devices", {"version": connection["version"], "source_device_id": "new-device"})
    post(h, path + "/imports", dict(body, digest=preview["digest"]), 409)
    assert h.edge.evidence(Scope(h.own.org, h.own.facility, connection["id"]))["items"] == []
