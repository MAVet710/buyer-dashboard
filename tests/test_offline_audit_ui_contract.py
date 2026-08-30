from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_inventory_audit_offline_capture_is_exact_scoped_and_visibly_uncommitted():
    audit_ui = (ROOT / "frontend/src/components/InventoryAudits.tsx").read_text(encoding="utf-8")
    queue = (ROOT / "frontend/src/lib/offlineQueue.ts").read_text(encoding="utf-8")

    assert "apiPostIdempotent" in audit_ui
    assert "queueOfflineMutation" in audit_ui
    assert "/scan/count/replay" in audit_ui
    assert 'safetyClass:"physical_capture"' in audit_ui
    assert "entityKey:target.line.id" in audit_ui
    assert "resolveOfflineAuditLine" in audit_ui
    assert "Offline matching is exact-only" in audit_ui
    assert "stores a local capture only" in audit_ui
    assert "It will not become a server count until verified replay succeeds." in audit_ui
    assert "APPROVED_REPLAY_ROUTES" in queue
    assert "scan\\/count\\/replay" in queue


def test_global_offline_status_replays_with_fresh_authenticated_idempotent_transport():
    status = (ROOT / "frontend/src/components/OfflineStatusBar.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert "replayOfflineMutations" in status
    assert "apiPostIdempotent(entry.path, entry.body, entry.idempotencyKey)" in status
    assert "operator review before it can be applied" in status
    assert '"X-Idempotency-Key": key' in api
    assert "authorizedFetch(path" in api
    assert "access_token" not in (ROOT / "frontend/src/lib/offlineQueue.ts").read_text(encoding="utf-8")
