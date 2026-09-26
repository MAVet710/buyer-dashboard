"""Standalone edge contract tests; never initialize application/cloud clients."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["COMAN_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AI_ALLOW_CLOUD_FALLBACK"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules" / "cultivation"))
from edge_store import EdgeBackpressure, EdgeError, EdgeStore, Scope

S = Scope("org", "facility", "connection")
START = "2026-09-26T00:00:00+00:00"
END = "2026-09-26T01:00:00+00:00"


def reading(event="1", at=START, value=77, **extra):
    return dict(event_id=event, source_device_id="device", source_channel="channel", source_metric="vendor_temp", value=value, unit="F", observed_at=at, quality="valid", **extra)


def mapping(**extra):
    return dict(organization_id="org", facility_id="facility", connection_id="connection", room_id="room", device_id="device-db", sensor_id="sensor-db", mapping_revision="v1", metric="temperature", effective_from=START, effective_to="2026-09-27T00:00:00+00:00", **extra)


@pytest.fixture
def store(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return EdgeStore(tmp_path / "edge.db")


def summary(store, **kwargs):
    return store.room_summary("org", "facility", "room", START, END, **kwargs)


def test_raw_fidelity_duplicates_conflict_and_scope(store):
    raw = reading(received_at="2026-09-26T00:00:05+00:00")
    assert store.ingest(S, [raw], [mapping()])["accepted"] == 1
    item = store.evidence(S)["items"][0]
    assert item["raw"] == raw
    assert item["canonical"]["value"] == 25
    assert item["snapshot"] == mapping()
    assert store.ingest(S, [dict(raw, received_at="2026-09-26T00:01:00+00:00")], [dict(mapping(), room_id="elsewhere")])["duplicates"] == 1
    assert store.evidence(S)["items"][0]["snapshot"]["room_id"] == "room"
    assert store.ingest(S, [dict(raw, value=78)], [mapping()])["conflicts"] == 1
    assert {r["state"] for r in store.evidence(S)["items"]} == {"disputed"}
    for wrong in (Scope("other", "facility", "connection"), Scope("org", "other", "connection"), Scope("org", "facility", "other")):
        assert store.evidence(wrong)["items"] == []
        assert store.diagnostics(wrong)["scope_rows"] == 0
        assert store.retry_pending(wrong, lambda *a: mapping())["examined"] == 0
        assert store.retention(wrong, "2027-01-01T00:00:00Z")["purged"] == 0


def test_restart_and_concurrent_replay(store):
    assert store.ingest(S, [reading()])["pending"] == 1
    restarted = EdgeStore(store.path)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: restarted.retry_pending(S, lambda s, r: mapping()), range(2)))
    assert sum(r["resolved"] for r in results) == 1
    assert restarted.evidence(S)["items"][0]["state"] == "ready"
    assert restarted.ingest(S, [reading()])["duplicates"] == 1


@pytest.mark.parametrize("field,value", [("value", float("nan")), ("value", float("inf")), ("value", 1e308), ("value", True), ("value", -1000), ("observed_at", "2026-09-26T00:00:00"), ("observed_at", None), ("event_id", None), ("quality", "invalid"), ("unit", "unknown")])
def test_invalid_evidence_quarantined(store, field, value):
    result = store.ingest(S, [dict(reading(), **{field: value})], [mapping()])
    assert result["quarantined"] == 1
    assert len(store.evidence(S)["items"]) == 1
    store.rollup(S, START, END)
    assert summary(store)["status"] == "UNKNOWN"
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 0


def test_mapping_scope_and_effective_interval(store):
    assert store.ingest(S, [reading()], [dict(mapping(), facility_id="other")])["quarantined"] == 1
    assert store.ingest(S, [reading("2")], [dict(mapping(), effective_to=START)])["quarantined"] == 1


def test_hold_gap_late_rebuild_and_deviation(store):
    snap = mapping(recipe_revision="recipe1", target_min=20, target_max=24, threshold_seconds=150)
    store.ingest(S, [reading()], [snap])
    assert store.rollup(S, START, END)["rebuilt"] == 1
    first = summary(store)["streams"][0]
    assert first["coverage_seconds"] == 300
    assert first["unknown_seconds"] == 3300
    assert first["above_seconds"] == 300
    assert first["deviations"][0]["seconds"] == 300
    old = store.pending_aggregates(S)["items"][0]
    store.ingest(S, [reading("2", "2026-09-26T00:02:00Z", 68)], [snap])
    assert not store.ack_aggregate(S, old["key"], old["revision"])
    store.rollup(S, START, END)
    result = summary(store)["streams"][0]
    newer = store.pending_aggregates(S)["items"][0]
    assert int(newer["revision"].split(":")[0]) > int(old["revision"].split(":")[0])
    assert result["coverage_seconds"] == 420
    assert result["above_seconds"] == 120
    assert result["in_target_seconds"] == 300
    assert result["deviations"] == []
    assert result["sample_mean"] == 22.5
    assert result["time_weighted_mean"] == pytest.approx((25*120+20*300)/420)
    assert store.rollup(S, START, END)["unchanged"] == 1


def test_invalid_sample_stops_hold_and_recipe_boundary(store):
    a = mapping(recipe_revision="r1", target_max=24)
    a["effective_to"] = "2026-09-26T00:01:00Z"
    b = dict(mapping(recipe_revision="r2", target_max=30), mapping_revision="v2", effective_from="2026-09-26T00:02:00Z", cycle_id="cycle")
    store.ingest(S, [reading(), reading("2", "2026-09-26T00:02:00Z"), dict(reading("3", "2026-09-26T00:03:00Z"), quality="invalid")], [a, b, b])
    store.rollup(S, START, END)
    rows = summary(store)["streams"]
    assert sorted(r["coverage_seconds"] for r in rows) == [60, 60]
    assert len(summary(store, cycle_id="cycle")["streams"]) == 1
    assert store.room_summary("other", "facility", "room", START, END)["streams"] == []


@pytest.mark.parametrize("metric,unit,value,total,kind", [("irrigation_event", "count", 1, 1, "event_total"), ("irrigation_volume", "mL", 500, .5, "volume_total"), ("irrigation_duration", "min", 2, 120, "duration_total")])
def test_event_volume_duration_totals(store, metric, unit, value, total, kind):
    store.ingest(S, [dict(reading(), unit=unit, value=value)], [dict(mapping(), metric=metric)])
    store.rollup(S, START, END)
    result = summary(store)["streams"][0]
    assert result["total"] == total
    assert result["total_kind"] == kind
    assert result["sample_mean"] is None and result["time_weighted_mean"] is None


def test_ppfd_partial_and_independent_sensors(store):
    for i in range(2):
        store.ingest(S, [dict(reading(str(i)), source_channel=str(i), unit="umol/m2/s", value=1000)], [dict(mapping(), metric="ppfd", sensor_id=str(i))])
    store.rollup(S, START, END)
    results = summary(store)["streams"]
    assert len(results) == 2
    assert all(r["measured_dli_contribution"] == .3 and r["dli_partial"] for r in results)


def test_double_drain_ack_restart_retention_and_tombstone(store):
    store.ingest(S, [reading()], [mapping()])
    assert store.retention(S, "2027-01-01T00:00:00Z")["protected"] == 1
    store.rollup(S, START, END)
    first = store.pending_aggregates(S)["items"][0]
    assert first == EdgeStore(store.path).pending_aggregates(S)["items"][0]
    assert not store.ack_aggregate(Scope("other", "facility", "connection"), first["key"], first["revision"])
    assert store.retention(S, "2027-01-01T00:00:00Z")["protected"] == 1
    assert store.ack_aggregate(S, first["key"], first["revision"])
    assert store.ack_aggregate(S, first["key"], first["revision"])
    before = summary(store)
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 1
    assert store.evidence(S)["items"][0]["raw"] is None
    assert summary(store) == before
    assert store.ingest(S, [reading()], [mapping()])["duplicates"] == 1
    assert store.ingest(S, [reading("late", "2026-09-26T00:01:00Z")], [mapping()])["quarantined"] == 1
    assert store.rollup(S, START, END)["blocked"] == 1
    assert summary(store)["status"] == "UNKNOWN"


def test_quotas_atomic_rollback_and_disk_backpressure(tmp_path):
    store = EdgeStore(tmp_path / "rows.db", max_scope_rows=1)
    with pytest.raises(EdgeBackpressure):
        store.ingest(S, [reading(), reading("2")])
    assert store.evidence(S)["items"] == []
    store = EdgeStore(tmp_path / "bytes.db", max_scope_bytes=1)
    with pytest.raises(EdgeBackpressure):
        store.ingest(S, [reading()])
    store = EdgeStore(tmp_path / "disk.db", max_disk_bytes=1)
    with pytest.raises(EdgeBackpressure):
        store.ingest(S, [reading()])
    assert store.evidence(S)["items"] == []


def test_bounded_queries_never_publish_partial(tmp_path):
    store = EdgeStore(tmp_path / "edge.db", max_query_rows=1)
    store.ingest(S, [reading(), reading("2", "2026-09-26T00:01:00Z")], [mapping(), mapping()])
    assert store.rollup(S, START, END)["truncated"]
    assert store.pending_aggregates(S)["items"] == []
    assert store.evidence(S, limit=1)["truncated"]
    for limit in (-1, 0, 501):
        with pytest.raises(EdgeError):
            store.evidence(S, limit=limit)
    with pytest.raises(EdgeError):
        store.room_summary("org", "facility", "room", START, "2026-09-26T01:00:01Z")


def test_secret_metadata_and_paths_are_not_exposed(store):
    secret = "super-private-secret"
    store.ingest(S, [reading(metadata={"Authorization": secret, "url": "https://host/?token="+secret})], [mapping()])
    result = json.dumps(store.evidence(S)) + json.dumps(store.diagnostics(S))
    assert secret not in result and "https://" not in result
    assert str(store.path) not in result
    assert store.evidence(S)["items"][0]["reason"] == "unsafe_metadata"


def test_transaction_failure_and_wal_restart(store):
    with pytest.raises(RuntimeError):
        with store._db(write=True) as db:
            db.execute("INSERT INTO buckets(scope,org,facility,start,key,revision,payload) VALUES(?,?,?,?,?,?,?)", (S.key, "org", "facility", 0, "k", "r", "{}"))
            raise RuntimeError("simulated_crash")
    assert EdgeStore(store.path).pending_aggregates(S)["items"] == []
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_cli_offline_collection(tmp_path):
    export = tmp_path / "input.json"
    export.write_text(json.dumps([reading()]))
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"columns": {k: k for k in reading()}, "metric_mappings": [{"source_metric": "vendor_temp", "unit": "F", "source_channel": "channel", "metric": "temperature"}]}))
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_cultivation_edge.py"
    args = [sys.executable, str(script), "--database", str(tmp_path / "cli.db"), "--organization", "org", "--facility", "facility", "--connection", "connection", "--input", str(export), "--contract", str(contract)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["pending"] == 1
    assert json.loads(subprocess.run(args, capture_output=True, text=True, timeout=30).stdout)["duplicates"] == 1


def test_concurrent_collectors_deduplicate(store):
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: store.ingest(S, [reading()], [mapping()]), range(4)))
    assert sum(r["accepted"] for r in results) == 1
    assert sum(r["duplicates"] for r in results) == 3


def test_corrected_mapping_replay_and_null_optional_targets(store):
    store.ingest(S, [reading()], [dict(mapping(), metric="unmapped")])
    assert store.retry_pending(S, lambda *a: mapping(target_min=None, threshold_seconds=None))["resolved"] == 1
    store.rollup(S, START, END)
    assert summary(store)["streams"][0]["coverage_seconds"] == 300


def test_pending_mapping_protects_neighbor_raw_from_purge(store):
    store.ingest(S, [reading(), reading("pending", "2026-09-26T00:10:00Z")], [mapping(), None])
    store.rollup(S, START, END)
    for aggregate in store.pending_aggregates(S)["items"]:
        store.ack_aggregate(S, aggregate["key"], aggregate["revision"])
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 0
    assert store.retry_pending(S, lambda *a: mapping())["resolved"] == 1


def test_conflict_dirties_old_and_new_timestamp_buckets(store):
    end = "2026-09-26T03:00:00Z"
    store.ingest(S, [reading()], [mapping()])
    store.rollup(S, START, end)
    store.ingest(S, [reading(at="2026-09-26T02:00:00Z")], [mapping()])
    assert store.room_summary("org", "facility", "room", START, end)["status"] == "UNKNOWN"
    store.rollup(S, START, end)
    assert store.room_summary("org", "facility", "room", START, end)["streams"] == []


def test_threshold_duration_merges_bucket_boundaries(store):
    end = "2026-09-26T02:00:00Z"
    snap = mapping(recipe_revision="recipe", target_max=24, threshold_seconds=240)
    store.ingest(S, [reading(at="2026-09-26T00:58:00Z")], [snap])
    store.rollup(S, START, end)
    result = store.room_summary("org", "facility", "room", START, end)["streams"][0]
    assert result["coverage_seconds"] == 300
    assert result["deviations"][0]["seconds"] == 300
    store.ingest(S, [reading("late", "2026-09-26T01:00:00Z", 68)], [snap])
    assert store.rollup(S, START, end)["rebuilt"] == 2
    assert store.room_summary("org", "facility", "room", START, end)["streams"][0]["deviations"] == []


@pytest.mark.parametrize("threshold", ["absent", None, 400])
def test_optional_threshold_preserves_bands_without_alerts(store, threshold):
    snap = mapping(recipe_revision="recipe", target_max=24)
    if threshold != "absent":
        snap["threshold_seconds"] = threshold
    store.ingest(S, [reading()], [snap])
    store.rollup(S, START, END)
    result = summary(store)["streams"][0]
    assert result["above_seconds"] == 300
    assert result["deviations"] == []
    assert result["alert_threshold_status"] == ("configured" if threshold == 400 else "not_configured")
    assert result["threshold_semantics"] == "continuous_same_direction"


def test_disconnected_excursions_do_not_accumulate_threshold(store):
    snap = mapping(recipe_revision="recipe", target_max=24, threshold_seconds=400)
    store.ingest(S, [reading(), reading("later", "2026-09-26T00:10:00Z")], [snap, snap])
    store.rollup(S, START, END)
    result = summary(store)["streams"][0]
    assert result["above_seconds"] == 600
    assert result["deviations"] == []


def test_stage_boundary_breaks_threshold_continuity(store):
    boundary = "2026-09-26T00:02:00Z"
    first = mapping(recipe_revision="recipe", target_max=24, threshold_seconds=400, stage_id="one")
    second = dict(first, stage_id="two", effective_from=boundary)
    store.ingest(S, [reading(), reading("next", boundary)], [first, second])
    store.rollup(S, START, END)
    results = summary(store)["streams"]
    assert sorted(r["above_seconds"] for r in results) == [120, 300]
    assert all(not r["deviations"] for r in results)


@pytest.mark.parametrize("value", [-1, .5, 2, True])
def test_invalid_state_never_normalized_to_truthy(store, value):
    assert store.ingest(S, [dict(reading(value=value), unit="bool")], [dict(mapping(), metric="hvac_state")])["quarantined"] == 1


def test_state_active_time_and_ec_registry_conversion(store):
    store.ingest(S, [dict(reading(value=1), unit="bool"), dict(reading("2", value=1500), source_channel="ec", unit="uS/cm")], [dict(mapping(), metric="hvac_state"), dict(mapping(), metric="substrate_ec", sensor_id="ec")])
    store.rollup(S, START, END)
    rows = {r["metric"]: r for r in summary(store)["streams"]}
    assert rows["hvac_state"]["active_seconds"] == 300
    assert rows["hvac_state"]["sample_mean"] is None
    assert rows["substrate_ec"]["time_weighted_mean"] == 1.5


def test_empty_room_is_unknown_and_limits_are_explicit(store):
    assert summary(store) == {"status": "UNKNOWN", "streams": [], "truncated": False, "start": START, "end": END}
    with pytest.raises(EdgeError):
        store.ack_aggregate(S, 1, "revision")
    with pytest.raises(EdgeError):
        summary(store, targets={"temperature": 25})
    with pytest.raises(EdgeError):
        EdgeStore(store.path, max_gap_seconds=1)
    assert store.rollup(S, START, "2026-10-20T00:00:00Z")["truncated"]


def test_abrupt_process_exit_rolls_back_and_imports_no_orm(tmp_path):
    database = tmp_path / "crash.db"
    store = EdgeStore(database)
    module_dir = Path(__file__).resolve().parents[1] / "modules" / "cultivation"
    program = '''import sys, os
sys.path.insert(0, sys.argv[1])
from edge_store import EdgeStore
assert "sqlalchemy" not in sys.modules
assert "requests" not in sys.modules
s = EdgeStore(sys.argv[2])
with s._db(write=True) as db:
    db.execute("INSERT INTO buckets(scope,org,facility,start,key,revision,payload) VALUES('scope','org','facility',0,'key','rev','{}')")
    os._exit(17)
'''
    result = subprocess.run([sys.executable, "-c", program, str(module_dir), str(database)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 17, result.stderr
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM buckets").fetchone()[0] == 0


def test_scope_connection_keeps_identical_source_streams_separate(store):
    other = Scope("org", "facility", "second")
    store.ingest(S, [reading()], [mapping()])
    store.ingest(other, [reading()], [dict(mapping(), connection_id="second")])
    store.rollup(S, START, END)
    store.rollup(other, START, END)
    assert len(summary(store)["streams"]) == 2
    assert {r["snapshot"]["connection_id"] for r in summary(store)["streams"]} == {"connection", "second"}


def test_snapshot_copy_is_immutable(store):
    snap = mapping()
    store.ingest(S, [reading()], [snap])
    snap["room_id"] = "changed"
    assert store.evidence(S)["items"][0]["snapshot"]["room_id"] == "room"
    assert store.retry_pending(S, lambda *a: snap)["examined"] == 0


def test_multiday_ppfd_is_not_daily_integral(store):
    store.ingest(S, [dict(reading(value=1000), unit="umol/m2/s")], [dict(mapping(), metric="ppfd")])
    end = "2026-09-28T00:00:00Z"
    store.rollup(S, START, end)
    result = store.room_summary("org", "facility", "room", START, end)["streams"][0]
    assert result["measured_dli_contribution"] is None
    assert result["measured_light_integral_mol_m2"] == .3
    assert result["dli_status"] == "NOT_DAILY_WINDOW"


def test_aggregate_and_room_response_byte_caps(store):
    payload = json.dumps({"streams": {}, "padding": "x" * 4300000})
    with store._db(write=True) as db:
        for i in range(2):
            db.execute("INSERT INTO buckets(scope,org,facility,start,key,revision,payload) VALUES(?,?,?,?,?,?,?)", (S.key, "org", "facility", 1790380800 + i*3600, str(i), "1:r", payload))
    pending = store.pending_aggregates(S)
    assert pending["truncated"] and len(pending["items"]) == 1
    result = store.room_summary("org", "facility", "room", START, "2026-09-26T02:00:00Z")
    assert result["truncated"] and result["streams"] == [] and result["status"] == "UNKNOWN"


def resolved_at(at, **changes):
    """Resolver-shaped per-reading hold, with approved historical context."""
    return dict(mapping(zone_id="zone", cycle_id="cycle", stage_id="flower",
                        recipe_revision="recipe", target_min=20, target_max=24,
                        threshold_seconds=400),
                effective_to=(datetime.fromisoformat(at.replace("Z", "+00:00")) + timedelta(seconds=300)).isoformat(),
                **changes)


def test_varying_resolved_holds_accumulate_across_buckets_and_rebuild(store, tmp_path):
    end = "2026-09-26T02:00:00Z"
    readings = [reading(str(i), at, value) for i, (at, value) in enumerate([
        ("2026-09-26T00:58:00Z", 77), ("2026-09-26T01:00:00Z", 86),
        ("2026-09-26T01:02:00Z", 77)])]
    snapshots = [resolved_at(r["observed_at"]) for r in readings]
    store.ingest(S, readings[::2], snapshots[::2])
    store.rollup(S, START, end)
    old = store.pending_aggregates(S)["items"]
    store.ingest(S, [readings[1]], [snapshots[1]])
    assert all(not store.ack_aggregate(S, a["key"], a["revision"]) for a in old)
    assert store.rollup(S, START, end)["rebuilt"] == 2
    result = store.room_summary("org", "facility", "room", START, end)
    assert len(result["streams"]) == 1
    row = result["streams"][0]
    assert row["sample_count"] == 3
    assert row["sample_mean"] == pytest.approx(80 / 3)
    assert row["time_weighted_mean"] == pytest.approx((25*420+30*120)/540)
    assert row["coverage_seconds"] == row["above_seconds"] == 540
    assert row["unknown_seconds"] == 7200 - 540
    assert row["deviations"][0]["seconds"] == 540
    assert len(row["attribution_intervals"]) == 1
    assert "effective_from" not in row["snapshot"] and "effective_to" not in row["snapshot"]
    assert {r["snapshot"]["effective_to"] for r in store.evidence(S)["items"]} == {s["effective_to"] for s in snapshots}
    ordered = EdgeStore(tmp_path / "ordered.db")
    ordered.ingest(S, readings, snapshots)
    ordered.rollup(S, START, END)
    ordered.rollup(S, END, end)
    assert ordered.room_summary("org", "facility", "room", START, end) == result
    assert [a["payload"] for a in store.pending_aggregates(S)["items"]] == [a["payload"] for a in ordered.pending_aggregates(S)["items"]]
    for a, previous in zip(store.pending_aggregates(S)["items"], old):
        if a["payload"] == previous["payload"]:
            assert a["revision"] == previous["revision"]
        else:
            assert int(a["revision"].split(":")[0]) > int(previous["revision"].split(":")[0])
        assert store.ack_aggregate(S, a["key"], a["revision"])
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 3
    assert store.room_summary("org", "facility", "room", START, end) == result


@pytest.mark.parametrize("change", [{"stage_id": "late-flower"}, {"mapping_revision": "v2"},
    {"sensor_id": "replacement"}, {"target_max": 23}, {"threshold_seconds": 500},
    {"recipe_revision": "recipe2"}, {"cycle_id": "cycle2"}, {"zone_id": "zone2"}])
def test_semantic_changes_split_and_clip_newly_learned_boundary(store, change):
    first, second = "2026-09-26T00:58:00Z", "2026-09-26T01:01:00Z"
    a = resolved_at(first)
    b = dict(resolved_at(second), effective_from="2026-09-26T00:59:00Z", **change)
    store.ingest(S, [reading("1", first)], [a])
    store.rollup(S, START, END)
    store.ingest(S, [reading("2", second)], [b])
    end = "2026-09-26T02:00:00Z"
    store.rollup(S, START, END)  # Separate windows must include bounded lookahead.
    store.rollup(S, END, end)
    rows = store.room_summary("org", "facility", "room", START, end)["streams"]
    assert len(rows) == 2
    assert sorted(r["coverage_seconds"] for r in rows) == [60, 300]
    assert sum(r["coverage_seconds"] for r in rows) <= 7200
    assert all(r["unknown_seconds"] + r["coverage_seconds"] == 7200 for r in rows)


def test_varying_holds_invalid_and_uncovered_gaps_are_not_bridged(store):
    ats = ["2026-09-26T00:00:00Z", "2026-09-26T00:01:00Z", "2026-09-26T00:02:00Z", "2026-09-26T00:10:00Z"]
    raws = [reading(str(i), at) for i, at in enumerate(ats)]
    raws[1]["quality"] = "invalid"
    snaps = [resolved_at(at) for at in ats]
    snaps[2]["effective_to"] = "2026-09-26T00:03:00Z"
    store.ingest(S, raws, snaps)
    store.rollup(S, START, END)
    rows = summary(store)["streams"]
    assert len(rows) == 1
    row = rows[0]
    assert row["sample_count"] == 3 and row["sample_mean"] == 25
    assert row["coverage_seconds"] == 420
    assert len(row["attribution_intervals"]) == 3
    assert row["deviations"] == []  # Each run falls short of 400 seconds.


def test_diagnostic_timestamps_are_scoped_validated_and_survive_retention(store):
    assert store.diagnostics(S)["last_received_at"] is None
    assert store.diagnostics(S)["last_valid_observed_at"] is None
    store.ingest(S, [reading(received_at="2000-01-01T00:00:00Z")])
    pending = store.diagnostics(S)
    assert pending["last_received_at"] != "2000-01-01T00:00:00+00:00"
    assert pending["last_valid_observed_at"] is None
    store.retry_pending(S, lambda *a: mapping())
    assert store.diagnostics(S)["last_valid_observed_at"] == START
    store.ingest(S, [dict(reading("bad", "2026-09-26T00:10:00Z"), quality="invalid")], [mapping()])
    assert store.diagnostics(S)["last_valid_observed_at"] == START
    assert store.diagnostics(S)["last_received_at"] >= pending["last_received_at"]
    for other in (Scope("other", "facility", "connection"), Scope("org", "other", "connection"), Scope("org", "facility", "other")):
        assert store.diagnostics(other)["last_received_at"] is None
        assert store.diagnostics(other)["last_valid_observed_at"] is None
    store.ingest(S, [reading("bad", "2026-09-26T00:10:00Z", 78)], [mapping()])
    assert store.diagnostics(S)["last_valid_observed_at"] == START
    # A dispute invalidates the formerly valid observation too.
    store.ingest(S, [reading(value=78)], [mapping()])
    assert store.diagnostics(S)["last_valid_observed_at"] is None


def test_version_one_buckets_fail_closed_and_preserve_generations(store):
    store.ingest(S, [reading()], [mapping()])
    store.rollup(S, START, END)
    original = store.pending_aggregates(S)["items"][0]
    with store._db(write=True) as db:
        payload = dict(original["payload"], calculation_version=1)
        db.execute("UPDATE buckets SET payload=?,ack=1", (json.dumps(payload),))
    upgraded = EdgeStore(store.path)
    assert upgraded.pending_aggregates(S)["items"] == []
    assert not upgraded.ack_aggregate(S, original["key"], original["revision"])
    assert summary(upgraded)["status"] == "UNKNOWN"
    upgraded.rollup(S, START, END)
    assert upgraded.pending_aggregates(S)["items"][0]["payload"]["calculation_version"] == 3
    with store._db(write=True) as db:
        db.execute("UPDATE buckets SET payload=?,purged=1", (json.dumps(payload),))
    upgraded = EdgeStore(store.path)
    assert upgraded.rollup(S, START, END)["blocked"] == 1
    assert upgraded.pending_aggregates(S)["items"] == []


@pytest.mark.parametrize("transition", [None, "stage", "mapping"])
def test_real_gateway_resolver_to_edge_accumulates_per_reading_holds(tmp_path, transition):
    # Exercise the actual resolver against an isolated relational database, then
    # persist its unmodified snapshots through the application EdgeStore import.
    from types import SimpleNamespace
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from modules.coman.models import Base, Organization, Facility, AppUser
    from modules.cultivation.models import CultivationRoom
    from modules.cultivation.gateway import TelemetryGatewayService
    from modules.cultivation.edge_store import EdgeStore as AppEdgeStore
    from modules.cultivation.intelligence_models import (
        TelemetryConnection, CultivationDevice, CultivationSensor, DeviceMapping,
        CropCycle, CropCycleRoom, CultivationRecipe, CultivationRecipeStage, CultivationRecipeTarget)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    at = datetime.fromisoformat(START)
    scoped = dict(organization_id="org", facility_id="facility")
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org", name="Edge test", slug="edge-test"))
        session.flush()
        session.add(Facility(id="facility", organization_id="org", name="Edge test", code="edge-test"))
        session.add(AppUser(id="actor", organization_id="org", username="edge-test", normalized_username="edge-test", password_hash="unusable-test-only", role="admin"))
        session.flush()
        session.add_all([
            CultivationRoom(id="room", **scoped, room_code="R"),
            TelemetryConnection(id="connection", **scoped, provider="json", label="File", created_by="actor"),
            CultivationDevice(id="device-db", **scoped, connection_id="connection", source_device_id="device"),
            CultivationSensor(id="sensor-db", **scoped, device_id="device-db", source_channel="channel", source_metric="vendor_temp", source_unit="F", metric="temperature", unit="C"),
            DeviceMapping(id="v1", **scoped, device_id="device-db", room_id="room", effective_at=at, created_by="actor"),
            CultivationRecipe(id="recipe", **scoped, name="Approved", version=1, status="approved", approved_at=at, approved_by="actor", created_by="actor"),
            CultivationRecipeStage(id="flower", **scoped, recipe_id="recipe", stage_key="flower", display_name="Flower", sequence=0),
            CultivationRecipeTarget(id="target", **scoped, stage_id="flower", metric="temperature", minimum=20, maximum=24, unit="C", threshold_seconds=1),
            CropCycle(id="cycle", **scoped, cycle_code="C", display_name="Cycle", recipe_id="recipe", created_by="actor"),
            CropCycleRoom(id="occupancy", **scoped, cycle_id="cycle", room_id="room", stage_id="flower", entered_at=at, assigned_by="actor"),
        ])
    edge = AppEdgeStore(tmp_path / "gateway-edge.db")
    service = TelemetryGatewayService(engine, SimpleNamespace(**scoped), edge=edge)
    scope = service._scope("connection")
    raws = [reading(str(i), (at + timedelta(minutes=58+2*i)).isoformat()) for i in range(3)]
    with Session(engine) as session:
        resolve = service._resolver(session, "connection")
        first = resolve(scope, raws[0])
    assert edge.ingest(scope, raws[:1], [first])["accepted"] == 1
    edge.rollup(scope, START, END)
    if transition:
        boundary = at + timedelta(minutes=59)
        with Session(engine) as session, session.begin():
            if transition == "mapping":
                session.add(DeviceMapping(id="v2", **scoped, device_id="device-db", room_id="room", effective_at=boundary, created_by="actor"))
            else:
                session.get(CropCycleRoom, "occupancy").exited_at = boundary
                session.add(CultivationRecipeStage(id="late-flower", **scoped, recipe_id="recipe", stage_key="late-flower", display_name="Late Flower", sequence=1))
                session.add(CultivationRecipeTarget(id="target2", **scoped, stage_id="late-flower", metric="temperature", minimum=20, maximum=24, unit="C", threshold_seconds=1))
                session.add(CropCycleRoom(id="occupancy2", **scoped, cycle_id="cycle", room_id="room", stage_id="late-flower", entered_at=boundary, assigned_by="actor"))
    with Session(engine) as session:
        resolve = service._resolver(session, "connection")
        snapshots = [first] + [resolve(scope, raw) for raw in raws[1:]]
    assert all(s is not None and s["recipe_revision"] == "recipe" for s in snapshots)
    assert len({s["effective_to"] for s in snapshots}) == 3
    assert edge.ingest(scope, raws[1:], snapshots[1:])["accepted"] == 2
    end = "2026-09-26T02:00:00Z"
    edge.rollup(scope, START, end)
    rows = edge.room_summary("org", "facility", "room", START, end)["streams"]
    assert len(rows) == (2 if transition else 1)
    assert sum(r["sample_count"] for r in rows) == 3
    assert all(r["sample_mean"] == 25 for r in rows)
    assert sorted(r["coverage_seconds"] for r in rows) == ([60, 420] if transition else [540])
    assert all(r["coverage_seconds"] == r["above_seconds"] for r in rows)
    assert all(r["deviations"][0]["seconds"] == r["coverage_seconds"] for r in rows)
    for aggregate in edge.pending_aggregates(scope)["items"]:
        edge.ack_aggregate(scope, aggregate["key"], aggregate["revision"])
    before = edge.diagnostics(scope)
    assert edge.retention(scope, "2027-01-01T00:00:00Z")["purged"] == 3
    assert edge.diagnostics(scope)["last_valid_observed_at"] == before["last_valid_observed_at"] == raws[-1]["observed_at"]
    assert edge.diagnostics(scope)["last_received_at"] == before["last_received_at"]
    engine.dispose()
