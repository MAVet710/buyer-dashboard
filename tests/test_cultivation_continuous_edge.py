"""Real isolated SQLite durability, maintenance and capacity regressions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules" / "cultivation"))
from edge_store import EdgeStore, Scope, EdgeBackpressure, EdgeError

S = Scope("org", "facility", "connection")
START = "2026-09-25T00:00:00+00:00"
END = "2026-09-25T01:00:00+00:00"


def reading(event="1", **kwargs):
    return dict(event_id=event, source_device_id="device", source_channel="channel", source_metric="temp", value=25, unit="C", observed_at=START, **kwargs)


def mapping(**kwargs):
    return dict(organization_id="org", facility_id="facility", connection_id="connection", room_id="room", device_id="device-db", sensor_id="sensor-db", mapping_revision="v1", metric="temperature", effective_from="2026-09-24T00:00:00Z", effective_to="2026-09-27T00:00:00Z", **kwargs)


def check_usage(store):
    with store._db() as db:
        assert store._usage(db, S.key) == store._recount_usage(db, S.key)


def test_usage_all_writers_rollback_and_legacy_reconciliation(tmp_path):
    store = EdgeStore(tmp_path / "e.db")
    store.ingest(S, [reading()])
    check_usage(store)
    store.retry_pending(S, lambda *_: mapping())
    check_usage(store)
    store.rollup(S, START, END)
    check_usage(store)
    (tmp_path / "archive").mkdir()
    store.archive_aggregates(S, tmp_path / "archive")
    store.retention(S, "2027-01-01T00:00:00Z")
    check_usage(store)
    store.ingest(S, [dict(reading(), value=26)])
    check_usage(store)
    with store._db() as db:
        before = store._usage(db, S.key)
    with pytest.raises(RuntimeError):
        with store._db(write=True) as db:
            db.execute("DELETE FROM evidence")
            db.execute("DELETE FROM buckets")
            raise RuntimeError()
    check_usage(store)
    with store._db(write=True) as db:
        assert store._usage(db, S.key) == before
        for table in ("evidence", "buckets"):
            for op in ("insert", "delete", "update"):
                db.execute(f"DROP TRIGGER edge_usage_{table}_{op}")
        db.execute("DROP TABLE edge_usage")
    reopened = EdgeStore(store.path)
    check_usage(reopened)
    with reopened._db() as db:
        assert reopened._usage(db, S.key) == before
    # Normal startup must not invoke the full recount.
    reopened._recount_usage = lambda *_: pytest.fail("rescan")
    reopened.ingest(S, [reading("new")])


@pytest.mark.parametrize("transport", [{}, {"batch_id": "b"}, {"batch_id": "b", "grant_id": "g", "secret": "x"}, {"batch_id": "x"*161, "grant_id": "g"}, {"batch_id": "b", "grant_id": None}])
def test_transport_metadata_rejected_atomically(tmp_path, transport):
    store = EdgeStore(tmp_path / "e.db")
    with pytest.raises(EdgeError):
        store.ingest(S, [reading()], transport=transport)
    assert store.evidence(S)["items"] == []
    assert store.transport_status(S)["last_committed_at"] is None


def test_transport_counters_scope_duplicates_and_whole_batch_rollback(tmp_path):
    store = EdgeStore(tmp_path / "e.db", max_scope_rows=3)
    transport = dict(batch_id="b", grant_id="g")
    store.ingest(S, [reading()], [mapping()], transport)
    valid = store.diagnostics(S)["last_valid_observed_at"]
    store.ingest(S, [reading()], transport=dict(transport, batch_id="retry"))
    store.ingest(S, [reading("pending")], transport=transport)
    store.ingest(S, [reading("bad", quality="invalid")], transport=transport)
    before = store.transport_status(S)
    assert (before["accepted_total"], before["duplicate_total"], before["pending_total"], before["quarantined_total"]) == (1, 1, 1, 1)
    with pytest.raises(EdgeBackpressure):
        store.ingest(S, [dict(reading(), value=26), reading("overflow")], transport=transport)
    assert store.transport_status(S) == before
    assert store.diagnostics(S)["last_valid_observed_at"] == valid
    assert store.transport_status(Scope("other", "facility", "connection"))["accepted_total"] == 0
    check_usage(store)
    store.max_scope_rows = 4
    store.ingest(S, [dict(reading(), value=26)], transport=transport)
    assert store.transport_status(S)["conflict_total"] == 1
    check_usage(store)


@pytest.mark.parametrize("crash", ["before", "after"])
def test_real_process_crash_and_lost_ack(tmp_path, crash):
    path = tmp_path / "e.db"
    store = EdgeStore(path)
    code = """
import os, sys
sys.path.insert(0, sys.argv[1])
from edge_store import EdgeStore, Scope
import json
s=EdgeStore(sys.argv[2]); scope=Scope('org','facility','connection')
if sys.argv[3]=='before':
    s._quota=lambda *a: os._exit(37)
s.ingest(scope,[json.loads(sys.argv[4])],transport={'batch_id':'b','grant_id':'g'})
os._exit(37)
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(Path(__file__).resolve().parents[1] / "modules" / "cultivation"), str(path), crash, json.dumps(reading())], timeout=8, capture_output=True)
    assert result.returncode == 37
    reopened = EdgeStore(path)
    assert reopened.transport_status(S)["pending_total"] == (crash == "after")
    retry = reopened.ingest(S, [reading()], transport=dict(batch_id="b", grant_id="g"))
    assert retry["duplicates" if crash == "after" else "pending"] == 1
    assert len(reopened.evidence(S)["items"]) == 1
    check_usage(reopened)


def test_pending_fairness_restart_and_resolver_outside_write_lock(tmp_path):
    store = EdgeStore(tmp_path / "e.db", busy_timeout_ms=100)
    store.ingest(S, [reading(str(n)) for n in range(8)])
    with store._db() as db:
        rows = db.execute("SELECT raw FROM evidence ORDER BY identity,fingerprint").fetchall()
    target = json.loads(rows[-1][0])["event_id"]
    def resolve(scope, raw):
        # A second independent writer can commit during resolution.
        with store._db(write=True) as db:
            db.execute("UPDATE edge_config SET config=config")
        return mapping() if raw["event_id"] == target else None
    total = 0
    for _ in range(5):
        total += store.retry_pending(S, resolve, limit=2)["resolved"]
        store = EdgeStore(store.path, busy_timeout_ms=100)
    assert total == 1
    check_usage(store)


def test_retention_protected_first_page_does_not_starve(tmp_path):
    store = EdgeStore(tmp_path / "e.db")
    store.ingest(S, [reading(str(n)) for n in range(6)])
    with store._db() as db:
        target = json.loads(db.execute("SELECT raw FROM evidence ORDER BY identity DESC LIMIT 1").fetchone()[0])["event_id"]
    store.retry_pending(S, lambda _, r: mapping() if r["event_id"] == target else None)
    # Unresolved neighbors normally protect all raw; move them outside this
    # bucket to isolate fairness while retaining their unresolved evidence.
    with store._db(write=True) as db:
        db.execute("UPDATE evidence SET observed=observed-86400 WHERE state='pending'")
    store.rollup(S, START, END)
    (tmp_path / "archive").mkdir()
    store.archive_aggregates(S, tmp_path / "archive")
    total = 0
    for _ in range(6):
        total += store.retention(S, "2027-01-01T00:00:00Z", limit=1)["purged"]
        store = EdgeStore(store.path)
    assert total == 1
    assert store.diagnostics(S)["counts"]["pending"] == 5
    check_usage(store)


def test_independent_reader_writer_bounded_and_full_durability(tmp_path):
    store = EdgeStore(tmp_path / "e.db", busy_timeout_ms=250)
    begin = time.monotonic()
    with store._db() as reader:
        reader.execute("SELECT COUNT(*) FROM evidence").fetchone()
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda n: store.ingest(S, [reading(str(n))]), range(8)))
        assert all(r["committed"] for r in results)
        assert reader.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        assert reader.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert time.monotonic()-begin < 10
    check_usage(store)


@pytest.mark.parametrize("limits", [{"max_rollup_rows": 1}, {"max_rollup_streams": 1}, {"max_query_rows": 1}])
def test_rollup_work_limits_never_publish_partial(tmp_path, limits):
    store = EdgeStore(tmp_path / "e.db", **limits)
    store.ingest(S, [reading(), dict(reading("2"), source_channel="other")], [mapping(), mapping()])
    assert store.rollup(S, START, END)["truncated"]
    assert store.pending_aggregates(S)["items"] == []
    check_usage(store)


def test_representative_18000_hour_boundary_out_of_order_benchmark(tmp_path):
    store = EdgeStore(tmp_path / "e.db")
    start = datetime.fromisoformat(START)
    data, snapshots = [], []
    metrics = [("temperature", "F", 77, 25), ("relative_humidity", "%", 55, 55),
               ("ppfd", "umol/m2/s", 600, 600), ("substrate_ec", "uS/cm", 2500, 2.5),
               ("irrigation_volume", "mL", 250, .25), ("hvac_state", "state", 1, 1)]
    for minute in range(-1, 61):
        for device in range(50):
            for metric in range(6):
                name, unit, value, canonical = metrics[metric]
                data.append(dict(reading(f"{minute}"), source_device_id=f"d{device}", source_channel=f"c{metric}", source_metric=name, unit=unit, value=value, observed_at=(start+timedelta(minutes=minute)).isoformat()))
                snapshots.append(dict(mapping(recipe_revision="recipe", target_max=canonical*.9, threshold_seconds=150), metric=name))
    begin = time.monotonic()
    # Reverse arrival order proves observation ordering, including lookahead.
    data.reverse()
    snapshots.reverse()
    for offset in range(0, len(data), 500):
        store.ingest(S, data[offset:offset+500], snapshots[offset:offset+500])
    ingest_seconds = time.monotonic()-begin
    begin = time.monotonic()
    assert store.rollup(S, START, END)["rebuilt"] == 1
    rollup_seconds = time.monotonic()-begin
    summary = store.room_summary("org", "facility", "room", START, END)
    assert len(summary["streams"]) == 300
    expected = {name: canonical for name, _, _, canonical in metrics}
    for stream in summary["streams"]:
        assert stream["sample_count"] == 60
        if stream["metric"] == "irrigation_volume":
            assert stream["total"] == 15
            assert stream["coverage_seconds"] == 0
            continue
        assert stream["coverage_seconds"] == stream["above_seconds"] == 3600
        if stream["metric"] == "hvac_state":
            assert stream["active_seconds"] == 3600
        else:
            assert stream["time_weighted_mean"] == stream["sample_mean"] == expected[stream["metric"]]
        assert stream["deviations"][0]["seconds"] == 3600
        if stream["metric"] == "ppfd":
            assert stream["measured_dli_contribution"] == 2.16
            assert stream["dli_partial"]
    check_usage(store)
    diagnostics = store.diagnostics(S)
    report = dict(readings=len(data), in_hour=18000, streams=300, ingest_seconds=ingest_seconds, rollup_seconds=rollup_seconds, sqlite=sqlite3.sqlite_version, scope_bytes=diagnostics["scope_bytes"], physical_bytes=diagnostics["capacity"]["physical_bytes"])
    (tmp_path / "benchmark.json").write_text(json.dumps(report, indent=2))
    print("EDGE_BENCHMARK="+json.dumps(report))
    assert diagnostics["capacity"]["projection_status"] == "unknown"


def test_capacity_projection_requires_measured_interval_and_warns(tmp_path):
    store = EdgeStore(tmp_path / "e.db", max_scope_rows=1000)
    store.ingest(S, [reading(str(n)) for n in range(200)])
    assert store.diagnostics(S)["capacity"]["projection_status"] == "unknown"
    now = time.time()
    with store._db(write=True) as db:
        db.execute("UPDATE edge_capacity_sample SET first_at=?,last_at=?,first_rows=0,first_bytes=0", (now-3601, now))
    capacity = store.diagnostics(S)["capacity"]
    assert capacity["projection_status"] == "observed_receipt_growth_scope_only"
    assert capacity["state"] == "warning"
    assert 0 < capacity["projected_headroom_seconds"] < 172800
    with store._db(write=True) as db:
        db.execute("UPDATE edge_capacity_sample SET last_at=?", (now-7200,))
    assert store.diagnostics(S)["capacity"]["projection_status"] == "unknown"
    store.max_scope_rows = 210
    assert store.diagnostics(S)["capacity"]["state"] == "critical"


def test_pinned_reader_disk_reserve_rolls_back_all_counters(tmp_path):
    store = EdgeStore(tmp_path / "e.db")
    store.ingest(S, [reading()], transport=dict(batch_id="first", grant_id="g"))
    before = store.transport_status(S)
    with store._db() as reader:
        reader.execute("SELECT COUNT(*) FROM evidence").fetchone()
        store.max_disk_bytes = 1
        with pytest.raises(EdgeBackpressure, match="disk_capacity_reached"):
            store.ingest(S, [reading("overflow")], transport=dict(batch_id="overflow", grant_id="g"))
    assert store.transport_status(S) == before
    assert len(store.evidence(S)["items"]) == 1
    check_usage(store)
