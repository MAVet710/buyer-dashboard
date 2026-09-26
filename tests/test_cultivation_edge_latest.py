"""Current local evidence is scoped, bounded and independent of rollups."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from modules.cultivation.edge_store import EdgeError, EdgeStore, Scope


SCOPE = Scope("org", "facility", "connection")


def setup(tmp_path, **kwargs):
    return EdgeStore(tmp_path / "latest.sqlite", **kwargs), datetime.now(timezone.utc) - timedelta(seconds=2)


def put(store, now, *, scope=SCOPE, room="room", sensor="sensor", channel="air", seconds=0,
        event="one", value=77, unit="F", quality="valid", target=True):
    snap = dict(organization_id=scope.organization_id, facility_id=scope.facility_id,
                connection_id=scope.connection_id, room_id=room, device_id="device", sensor_id=sensor,
                mapping_revision="mapping", metric="temperature", cycle_id="cycle", stage_id="stage",
                effective_from=(now - timedelta(days=1)).isoformat(),
                effective_to=(now + timedelta(days=2)).isoformat())
    if target:
        snap.update(recipe_revision="approved", target_min=20, target_max=26)
    raw = dict(event_id=event, source_device_id=sensor, source_channel=channel,
               source_metric="temperature", value=value, unit=unit, quality=quality,
               observed_at=(now - timedelta(seconds=seconds)).isoformat(),
               received_at=(now - timedelta(days=5)).isoformat())
    return store.ingest(scope, [raw], [snap])


def latest(store, now, **kwargs):
    return store.latest("org", "facility", "room", now=now, **kwargs)


def test_current_hour_independent_fresh_stale_and_original_fidelity(tmp_path):
    store, now = setup(tmp_path)
    put(store, now, sensor="fresh")
    put(store, now, sensor="stale", seconds=301)
    result = latest(store, now)
    fresh, stale = result["readings"]
    assert result["status"] == "UNKNOWN" and not result["truncated"]
    assert (fresh["status"], stale["status"]) == ("in_target", "stale")
    assert (fresh["value"], fresh["unit"], fresh["original_value"], fresh["original_unit"]) == (25, "C", 77, "F")
    assert datetime.fromisoformat(fresh["received_at"]) > now
    assert fresh["latency_seconds"] >= 0 and fresh["data_age_seconds"] == 0
    assert fresh["snapshot"]["cycle_id"] == "cycle"
    with store._db() as db:
        assert db.execute("SELECT COUNT(*) FROM buckets").fetchone()[0] == 0


@pytest.mark.parametrize("bad", [{"quality": "invalid"}, {"value": "NaN"}, {"unit": "unsupported"}, {"seconds": -3600}])
def test_latest_invalid_is_not_masked(tmp_path, bad):
    store, now = setup(tmp_path)
    put(store, now, event="old", seconds=60)
    put(store, now, event="bad", **bad)
    reading = latest(store, now)["readings"][0]
    assert reading["state"] == "quarantined"
    assert reading["status"] == "invalid" and reading["value"] is None
    if bad.get("seconds"):
        assert latest(store, now + timedelta(hours=2))["readings"][0]["status"] == "invalid"


def test_exact_scope_room_and_connection_collision(tmp_path):
    store, now = setup(tmp_path)
    put(store, now)
    put(store, now, scope=Scope("other", "facility", "connection"), value=90)
    put(store, now, scope=Scope("org", "other", "connection"), value=90)
    put(store, now, room="other", event="other", value=90)
    put(store, now, scope=Scope("org", "facility", "second"))
    put(store, now, channel="second", event="second")
    readings = latest(store, now)["readings"]
    assert len(readings) == 3
    assert {r["connection_id"] for r in readings} == {"connection", "second"}
    assert all(r["value"] == 25 and r["snapshot"]["room_id"] == "room" for r in readings)


def test_out_of_order_and_dispute(tmp_path):
    store, now = setup(tmp_path)
    put(store, now, event="new", value=68)
    put(store, now, event="old", seconds=100)
    assert latest(store, now)["readings"][0]["value"] == 20
    put(store, now, event="new", value=69)
    assert latest(store, now)["readings"][0]["status"] == "invalid"


def test_invalid_measurement_snapshot_remains_immutable_on_retry(tmp_path):
    store, now = setup(tmp_path)
    put(store, now, unit="unsupported")
    before = latest(store, now)["readings"][0]

    def resolver(*args):
        pytest.fail("An already validated snapshot must not be replaced")

    assert store.retry_pending(SCOPE, resolver)["resolved"] == 0
    assert latest(store, now)["readings"][0] == before


def test_unconfigured_empty_expired_and_missing_raw(tmp_path):
    store, now = setup(tmp_path)
    assert latest(store, now) == dict(as_of=now.isoformat(), readings=[], truncated=False, status="UNKNOWN")
    put(store, now, target=False)
    assert latest(store, now)["readings"][0]["status"] == "unconfigured"
    assert latest(store, now + timedelta(days=3))["readings"][0]["status"] == "unavailable"
    with store._db(write=True) as db:
        db.execute("UPDATE evidence SET canonical=NULL")
    assert latest(store, now)["readings"][0]["status"] == "unavailable"
    with store._db(write=True) as db:
        db.execute("UPDATE evidence SET raw=NULL,state='archived'")
    reading = latest(store, now)["readings"][0]
    assert reading["status"] == "unavailable"
    assert reading["original_value"] is None and reading["value"] is None


def test_bounded_candidates_streams_and_index(tmp_path):
    store, now = setup(tmp_path, max_query_rows=2)
    put(store, now, sensor="unseen", seconds=100)
    for i in range(3):
        put(store, now, event=str(i), seconds=i)
    result = latest(store, now)
    assert result["truncated"] and len(result["readings"]) == 1
    with store._db() as db:
        plan = db.execute("""EXPLAIN QUERY PLAN SELECT * FROM evidence
            WHERE json_extract(scope,'$.organization_id')=? AND json_extract(scope,'$.facility_id')=?
            AND json_extract(snapshot,'$.room_id')=?
            ORDER BY COALESCE(observed,received) DESC,identity DESC,fingerprint DESC LIMIT ?""",
            ("org", "facility", "room", 3)).fetchall()
    assert "edge_latest_room" in str([tuple(r) for r in plan])
    assert "TEMP B-TREE" not in str([tuple(r) for r in plan])
    store.max_query_rows = 10000
    for i in range(202):
        put(store, now, sensor=f"sensor{i}")
    result = latest(store, now)
    assert len(result["readings"]) == 200 and result["truncated"]
    assert len(latest(store, now, limit=1)["readings"]) == 1
    for invalid in (0, 201, True, 1.5):
        with pytest.raises(EdgeError, match="invalid_limit"):
            latest(store, now, limit=invalid)


def test_unmapped_cannot_borrow_room_and_output_has_no_metadata(tmp_path):
    store, now = setup(tmp_path)
    put(store, now)
    with store._db() as db:
        raw = json.loads(db.execute("SELECT raw FROM evidence").fetchone()[0])
    raw.update(event_id="pending", observed_at=now.isoformat())
    store.ingest(SCOPE, [raw])
    result = latest(store, now)
    assert len(result["readings"]) == 1 and result["status"] == "UNKNOWN"
    assert not ({"raw", "metadata", "path", "deviations"} & result["readings"][0].keys())
