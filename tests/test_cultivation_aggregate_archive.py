"""Local receiver and retention integration, with no network or application init."""
from copy import deepcopy
import json
import os

import pytest

from tests.test_cultivation_edge_store import S, START, END, reading, mapping, store
from edge_store import EdgeError, EdgeStore, Scope, _hash
import aggregate_archive as archive


@pytest.fixture
def archive_dir(tmp_path):
    result = tmp_path / "archive"
    result.mkdir()
    return result


def prepare(store, scope=S):
    snap = dict(mapping(), organization_id=scope.organization_id,
                facility_id=scope.facility_id, connection_id=scope.connection_id)
    store.ingest(scope, [reading()], [snap])
    store.rollup(scope, START, END)
    return store.pending_aggregates(scope)["items"][0]


def artifact(root, scope, item):
    return root / _hash(archive.asdict(scope)) / item["key"] / (item["revision"].split(":")[0] + ".json")


def test_durable_archive_allows_retention_and_restart_dedup(store, archive_dir):
    item = prepare(store)
    clocks = store.diagnostics(S)
    assert store.retention(S, "2027-01-01T00:00:00Z")["protected"] == 1
    result = store.archive_aggregates(S, archive_dir)
    assert result == dict(archived=1, acknowledged=1, stale=0, truncated=False)
    saved = json.loads(artifact(archive_dir, S, item).read_text(encoding="utf-8"))
    assert set(saved) == {"scope", "key", "revision", "payload"}
    assert "raw" not in saved and "canonical" not in saved
    restarted = EdgeStore(store.path)
    assert restarted.retention(S, "2027-01-01T00:00:00Z")["purged"] == 1
    assert restarted.ingest(S, [reading()], [mapping()])["duplicates"] == 1
    assert restarted.ingest(S, [reading("late", "2026-09-26T00:01:00Z")], [mapping()])["quarantined"] == 1
    assert restarted.diagnostics(S)["last_valid_observed_at"] == clocks["last_valid_observed_at"]


def test_receiver_replay_after_acceptance_before_ack_and_cross_scope(store, archive_dir):
    first = prepare(store)
    archive.accept_aggregate(S, archive_dir, first)
    restarted = EdgeStore(store.path)
    assert restarted.archive_aggregates(S, archive_dir)["acknowledged"] == 1
    for other in (Scope("other", "facility", "connection"), Scope("org", "other", "connection"), Scope("org", "facility", "other")):
        item = prepare(restarted, other)
        assert restarted.archive_aggregates(other, archive_dir)["acknowledged"] == 1
        assert artifact(archive_dir, other, item) != artifact(archive_dir, S, first)
        with pytest.raises(EdgeError, match="archive_invalid_aggregate"):
            archive.accept_aggregate(other, archive_dir, first)


@pytest.mark.parametrize("failure", ["corrupt", "fsync", "replace", "readback"])
def test_archive_failure_never_acknowledges_or_purges(store, archive_dir, monkeypatch, failure):
    item = prepare(store)
    if failure == "corrupt":
        archive.accept_aggregate(S, archive_dir, item)
        artifact(archive_dir, S, item).write_text("{}")
    elif failure == "readback":
        original = archive._replace
        def corrupt(source, target):
            original(source, target)
            target.write_text("{}")
        monkeypatch.setattr(archive, "_replace", corrupt)
    else:
        def fail(*args):
            raise OSError("sensitive local path must not escape")
        monkeypatch.setattr(archive.os if failure == "fsync" else archive,
                            "fsync" if failure == "fsync" else "_replace", fail)
    with pytest.raises(EdgeError) as error:
        store.archive_aggregates(S, archive_dir)
    assert str(error.value) in {"archive_artifact_conflict", "archive_storage_unavailable", "archive_readback_failed"}
    assert len(store.pending_aggregates(S)["items"]) == 1
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 0


@pytest.mark.parametrize("rebuild", [False, True])
def test_dirty_or_new_revision_during_archive_is_not_acknowledged(store, archive_dir, monkeypatch, rebuild):
    old = prepare(store)
    original = archive.accept_aggregate
    def concurrent(scope, root, item):
        original(scope, root, item)
        store.ingest(S, [reading("late", "2026-09-26T00:02:00Z", 68)], [mapping()])
        if rebuild:
            store.rollup(S, START, END)
    monkeypatch.setattr(archive, "accept_aggregate", concurrent)
    assert store.archive_aggregates(S, archive_dir)["stale"] == 1
    assert not store.ack_aggregate(S, old["key"], old["revision"])
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 0


@pytest.mark.parametrize("mutation", ["scope", "hash", "generation", "raw", "snapshot", "key"])
def test_receiver_validates_every_snapshot_and_envelope(store, archive_dir, mutation):
    item = deepcopy(prepare(store))
    entry = next(iter(item["payload"]["streams"].values()))
    if mutation == "scope":
        entry["snapshot"]["connection_id"] = "other"
    elif mutation == "raw":
        entry["raw"] = "forbidden"
    elif mutation == "snapshot":
        entry["snapshot"]["provider_body"] = "forbidden"
    elif mutation == "key":
        item["key"] = "bad"
    item["revision"] = ("0" * 20 if mutation == "generation" else "00000000000000000001") + ":" + ("0" * 64 if mutation == "hash" else _hash(item["payload"]))
    with pytest.raises(EdgeError, match="archive_invalid_aggregate"):
        archive.accept_aggregate(S, archive_dir, item)
    assert not list(archive_dir.rglob("*.json"))


def test_path_hazards_and_explicit_absolute_root(store, archive_dir):
    prepare(store)
    for path in ("relative", archive_dir / ".." / "archive", archive_dir / "missing"):
        with pytest.raises(EdgeError):
            store.archive_aggregates(S, path)
    target = archive_dir / "junction"
    if os.name == "nt":
        import subprocess
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(archive_dir)], capture_output=True)
        assert completed.returncode == 0
    else:
        target.symlink_to(archive_dir, target_is_directory=True)
    try:
        with pytest.raises(EdgeError, match="archive_unsafe_path"):
            store.archive_aggregates(S, target)
    finally:
        target.rmdir() if os.name == "nt" else target.unlink()


def test_bounded_archive_and_retention_keep_pending_protected(store, archive_dir):
    prepare(store)
    store.rollup(S, END, "2026-09-26T02:00:00Z")
    assert store.archive_aggregates(S, archive_dir, limit=1)["truncated"]
    store.ingest(S, [reading("pending", "2026-09-26T00:01:00Z")])
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 0


def test_generation_conflict_and_stale_delivery_preserve_newer_artifact(store, archive_dir):
    old = prepare(store)
    archive.accept_aggregate(S, archive_dir, old)
    store.ingest(S, [reading("late", "2026-09-26T00:02:00Z", 68)], [mapping()])
    store.rollup(S, START, END)
    newer = store.pending_aggregates(S)["items"][0]
    archive.accept_aggregate(S, archive_dir, newer)
    archive.accept_aggregate(S, archive_dir, old)
    assert json.loads(artifact(archive_dir, S, newer).read_text())["revision"] == newer["revision"]
    conflict = deepcopy(newer)
    conflict["revision"] = old["revision"].split(":")[0] + ":" + _hash(conflict["payload"])
    with pytest.raises(EdgeError, match="archive_artifact_conflict"):
        archive.accept_aggregate(S, archive_dir, conflict)


def test_receiver_lock_contention_fails_closed_and_restart_releases(store, archive_dir):
    prepare(store)
    with archive._receiver_lock(archive_dir):
        with pytest.raises(EdgeError, match="archive_storage_unavailable"):
            store.archive_aggregates(S, archive_dir)
        assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 0
    assert EdgeStore(store.path).archive_aggregates(S, archive_dir)["acknowledged"] == 1


def test_hardlinked_artifact_fails_closed(store, archive_dir):
    item = prepare(store)
    archive.accept_aggregate(S, archive_dir, item)
    os.link(artifact(archive_dir, S, item), archive_dir / "linked")
    with pytest.raises(EdgeError, match="archive_unsafe_path"):
        store.archive_aggregates(S, archive_dir)
    assert store.retention(S, "2027-01-01T00:00:00Z")["purged"] == 0
