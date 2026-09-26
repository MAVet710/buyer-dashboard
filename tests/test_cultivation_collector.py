"""Finalized-file collector tests: local files and SQLite only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules" / "cultivation"))
from edge_store import EdgeStore, Scope, EdgeBackpressure, EdgeError
from collector import FileCollector, _open_file
from adapters.normalized import NormalizedExportAdapter

S = Scope("org", "facility", "connection")
ROW = dict(event_id="original-1", source_device_id="device", source_channel="temp", source_metric="temperature", value=25, unit="C", observed_at="2026-09-25T00:00:00Z")
CONTRACT = dict(columns={k: k for k in ROW}, metric_mappings=[dict(source_metric="temperature", unit="C", source_channel="temp", metric="temperature")])


def make(tmp_path, **kwargs):
    directory = tmp_path / "input"
    directory.mkdir(exist_ok=True)
    store = EdgeStore(tmp_path / "edge.db")
    collector = FileCollector(store, S, directory, NormalizedExportAdapter(**CONTRACT), **kwargs)
    return store, collector, directory


def publish(directory, rows=None, name="sample"):
    temporary = directory / (name+".part")
    temporary.write_text(json.dumps([ROW] if rows is None else rows), encoding="utf-8")
    ready = directory / (name+".ready.json")
    temporary.replace(ready)
    return ready


def test_finalized_atomic_publish_restart_original_preserved(tmp_path):
    store, collector, directory = make(tmp_path)
    partial = directory / "sample.part"
    partial.write_text("[")
    assert collector.run(once=True)["committed_files"] == 0
    ready = publish(directory)
    original = ready.read_bytes()
    assert collector.run(once=True)["committed_files"] == 1
    assert store.evidence(S)["items"][0]["raw"]["event_id"] == ROW["event_id"]
    assert store.evidence(S)["items"][0]["state"] == "pending"
    restarted = FileCollector(EdgeStore(store.path), S, directory, collector.adapter)
    assert restarted.run(once=True)["skipped"] == 1
    assert ready.read_bytes() == original
    assert store.transport_status(S)["last_committed_at"] is None


@pytest.mark.parametrize("bad", [{k: v for k, v in ROW.items() if k != "event_id"}, dict(ROW, event_id="https://invalid"), dict(ROW, extra="metadata"), dict(ROW, source_metric="unconfigured"), dict(ROW, source_device_id=None)])
def test_invalid_identity_metadata_contract_durable_hold(tmp_path, bad):
    store, collector, directory = make(tmp_path)
    publish(directory, [bad])
    assert collector.run(once=True)["held_files"] == 1
    restarted = FileCollector(EdgeStore(store.path), S, directory, collector.adapter)
    assert restarted.run(once=True)["skipped"] == 1
    assert store.evidence(S)["items"] == []
    with store._db() as db:
        assert db.execute("SELECT COUNT(*) FROM edge_collector_files").fetchone()[0] == 1


def test_full_quota_no_cursor_then_retry(tmp_path):
    store, collector, directory = make(tmp_path)
    store.max_scope_rows = 1
    publish(directory, [ROW, dict(ROW, event_id="2")])
    assert collector.run(once=True)["transient_errors"] == 1
    assert store.evidence(S)["items"] == []
    with store._db() as db:
        assert db.execute("SELECT COUNT(*) FROM edge_collector_files").fetchone()[0] == 0
    store.max_scope_rows = 2
    assert collector.run(once=True)["committed_files"] == 1


def test_commit_lost_source_ack_replays_exactly(tmp_path, monkeypatch):
    store, collector, directory = make(tmp_path)
    publish(directory)
    original = collector._record
    monkeypatch.setattr(collector, "_record", lambda *a: (_ for _ in ()).throw(OSError()))
    assert collector.run(once=True)["transient_errors"] == 1
    assert len(store.evidence(S)["items"]) == 1
    monkeypatch.setattr(collector, "_record", original)
    assert collector.run(once=True)["committed_files"] == 1
    assert len(store.evidence(S)["items"]) == 1


def test_singleton_lock_and_release(tmp_path):
    store, collector, directory = make(tmp_path)
    alternate = str(directory).upper() if os.name == "nt" else directory
    second = FileCollector(store, S, alternate, collector.adapter)
    with collector.exclusive():
        with pytest.raises(EdgeBackpressure, match="collector_already_running"):
            second.run(once=True)
    second.run(once=True)


def test_bounded_scan_and_manifest_capacity(tmp_path):
    store, collector, directory = make(tmp_path, max_scan=2, max_files=1, max_source_files=2)
    for n in range(4):
        publish(directory, [dict(ROW, event_id=str(n))], str(n))
    reports = []
    collector.poll_seconds = .001
    collector.run(max_iterations=6, report=reports.append)
    assert all(r["scanned"] <= 2 and r["committed_files"] <= 1 for r in reports)
    assert len(store.evidence(S)["items"]) == 2
    assert any(r["transient_errors"] for r in reports)


def test_stop_interrupts_backoff_and_transient_recovers(tmp_path, monkeypatch):
    _, collector, directory = make(tmp_path, poll_seconds=.01, backoff_cap=1)
    publish(directory)
    original = collector.store.ingest
    calls = []
    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise EdgeBackpressure("test_unavailable")
        return original(*args, **kwargs)
    monkeypatch.setattr(collector.store, "ingest", flaky)
    reports = []
    collector.run(max_iterations=4, report=reports.append)
    assert any(r["transient_errors"] for r in reports)
    assert any(r["committed_files"] for r in reports)
    stop = threading.Event()
    collector.poll_seconds = 60
    start = time.monotonic()
    thread = threading.Thread(target=collector.run, kwargs=dict(stop=stop))
    thread.start()
    stop.set()
    thread.join(2)
    assert not thread.is_alive() and time.monotonic()-start < 2


def test_size_and_row_limits_hold_no_partial(tmp_path):
    store, collector, directory = make(tmp_path)
    collector.adapter.max_bytes = 10
    publish(directory)
    assert collector.run(once=True)["held_files"] == 1
    assert store.evidence(S)["items"] == []
    collector.adapter.max_bytes = 10000
    collector.adapter.max_rows = 1
    publish(directory, [ROW, dict(ROW, event_id="2")], "two")
    assert collector.run(once=True)["held_files"] == 1
    assert store.evidence(S)["items"] == []


def test_windows_open_blocks_partial_writer(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows sharing contract")
    store, collector, directory = make(tmp_path)
    ready = publish(directory)
    with ready.open("r+b") as writer:
        writer.seek(0)
        writer.write(b"[")
        writer.flush()
        assert collector.run(once=True)["transient_errors"] == 1
    assert collector.run(once=True)["committed_files"] == 1
    with _open_file(ready):
        with pytest.raises(OSError):
            ready.open("wb")


def test_reparse_rejected_without_consumption(tmp_path, monkeypatch):
    store, collector, directory = make(tmp_path)
    publish(directory)
    import collector as module
    original = module._plain_path
    def reject(path):
        if str(path).endswith("ready.json"):
            raise EdgeError("collector_link_rejected")
        return original(path)
    monkeypatch.setattr(module, "_plain_path", reject)
    assert collector.run(once=True)["held_files"] == 1
    assert store.evidence(S)["items"] == []


def test_csv_explicit_contract(tmp_path):
    store, collector, directory = make(tmp_path, format="csv")
    source = directory / "sample.ready.csv"
    source.write_text(",".join(ROW)+"\n"+",".join(str(v) for v in ROW.values())+"\n")
    assert collector.run(once=True)["committed_files"] == 1
    assert store.evidence(S)["items"][0]["raw"]["value"] == "25"


def test_cli_watch_standalone_bounded_iterations(tmp_path):
    _, _, directory = make(tmp_path)
    publish(directory)
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(CONTRACT))
    root = Path(__file__).resolve().parents[1]
    # Execute CLI in-process inside a fresh isolated interpreter so imports
    # are inspected without relying only on source-string assertions.
    code = """
import runpy,sys
sys.argv=sys.argv[1:]
try: runpy.run_path(sys.argv[0],run_name='__main__')
except SystemExit as e:
    assert e.code==0
assert 'sqlalchemy' not in sys.modules and 'dotenv' not in sys.modules
assert 'modules.cultivation' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(root / "scripts/run_cultivation_edge.py"), "--database", str(tmp_path / "cli.db"), "--organization", "org", "--facility", "facility", "--connection", "connection", "--input", str(directory), "--contract", str(contract), "--watch", "--max-iterations", "2", "--poll-seconds", ".01"], capture_output=True, text=True, timeout=8)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 2


@pytest.mark.parametrize("crash", ["before", "after"])
def test_collector_process_crash_source_marker_recovery(tmp_path, crash):
    store, collector, directory = make(tmp_path)
    publish(directory)
    code = """
import sys,os,json
sys.path.insert(0,sys.argv[1])
from collector import FileCollector
from edge_store import EdgeStore,Scope
from adapters.normalized import NormalizedExportAdapter
s=EdgeStore(sys.argv[2]); c=FileCollector(s,Scope('org','facility','connection'),sys.argv[3],NormalizedExportAdapter(**json.loads(sys.argv[4])))
if sys.argv[5]=='before': s._quota=lambda *a: os._exit(41)
else: c._record=lambda *a: os._exit(41)
c.run(once=True)
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(Path(__file__).resolve().parents[1] / "modules/cultivation"), str(store.path), str(directory), json.dumps(CONTRACT), crash], timeout=8, capture_output=True)
    assert result.returncode == 41, result.stderr
    assert len(store.evidence(S)["items"]) == (crash == "after")
    with store._db() as db:
        assert db.execute("SELECT COUNT(*) FROM edge_collector_files").fetchone()[0] == 0
    assert collector.run(once=True)["committed_files"] == 1
    assert len(store.evidence(S)["items"]) == 1


def test_real_hardlink_and_traversal_rejected(tmp_path):
    store, collector, directory = make(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps([ROW]))
    os.link(outside, directory / "hard.ready.json")
    assert collector.run(once=True)["held_files"] == 1
    assert store.evidence(S)["items"] == []
    with pytest.raises(EdgeError, match="unsafe_path"):
        FileCollector(store, S, directory / ".." / "input", collector.adapter)


def test_changed_finalized_file_keeps_original_identity_conflict(tmp_path):
    store, collector, directory = make(tmp_path)
    publish(directory)
    collector.run(once=True)
    publish(directory, [dict(ROW, value=26)])
    collector.run(once=True)
    assert {r["state"] for r in store.evidence(S)["items"]} == {"disputed"}


def test_corrected_contract_retries_unchanged_held_file_without_replaying_committed(tmp_path):
    store, collector, directory = make(tmp_path)
    raw = dict(ROW, source_metric="vendor_temp")
    source = publish(directory, [raw])
    original = source.read_bytes()
    assert collector.run(once=True)["held_files"] == 1
    fixed = dict(CONTRACT, metric_mappings=[dict(source_metric="vendor_temp", unit="C", source_channel="temp", metric="temperature")])
    corrected = FileCollector(store, S, directory, NormalizedExportAdapter(**fixed))
    assert corrected.lock_path == collector.lock_path
    assert corrected.run(once=True)["committed_files"] == 1
    assert len(store.evidence(S)["items"]) == 1
    assert source.read_bytes() == original
    assert corrected.run(once=True)["skipped"] == 1
    # A subsequent interpretation change cannot silently reinterpret old commits.
    assert collector.run(once=True)["skipped"] == 1
    assert len(store.evidence(S)["items"]) == 1
