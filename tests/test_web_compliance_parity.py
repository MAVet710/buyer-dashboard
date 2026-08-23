from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.database import get_engine
from backend.app.main import app
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from tests.test_web_inventory_api import _engine


ROOT = Path(__file__).resolve().parents[1]


def _reconciliation_transaction(engine):
    repository = TraceabilityBackofficeRepository(engine)
    transaction = repository.create_transaction(
        organization_id="org-1",
        facility_id="facility-1",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A406030000WEB001",
        idempotency_key="web-compliance-parity-1",
        actor="operator@example.com",
        license_number="MR281234",
        request_payload={"package": "1A406030000WEB001", "user_api_key": "must-not-persist"},
    )
    for status in ("validated", "queued", "submitted", "reconciliation_required"):
        transaction = repository.transition_logged(
            organization_id="org-1",
            facility_id="facility-1",
            transaction_id=transaction.id,
            new_status=status,
            actor="traceability-worker",
            reason="External quantity differs" if status == "reconciliation_required" else f"Advance to {status}",
            source="system",
            error_message="Buyer Dash and METRC quantities differ" if status == "reconciliation_required" else "",
        )
    return transaction


def test_traceability_api_preserves_filters_detail_payloads_confirmation_and_tenant_scope():
    engine = _engine()
    transaction = _reconciliation_transaction(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "qa@example.com", "X-User-Role": "qa"}
    try:
        queue = client.get("/api/v1/compliance/traceability?status=rejected&status=reconciliation_required&provider=metrc", headers=headers)
        detail = client.get(f"/api/v1/compliance/traceability/{transaction.id}", headers=headers)
        unconfirmed = client.post(f"/api/v1/compliance/traceability/{transaction.id}/resolve", headers=headers, json={"action": "requeue", "reason": "Reviewed state", "confirmed": False})
        resolved = client.post(f"/api/v1/compliance/traceability/{transaction.id}/resolve", headers=headers, json={"action": "requeue", "reason": "Reviewed state", "confirmed": True})
        isolated = client.get(f"/api/v1/compliance/traceability/{transaction.id}", headers={**headers, "X-Facility-Id": "other-facility"})
    finally:
        app.dependency_overrides.clear()
    assert queue.status_code == 200
    assert queue.json()["items"][0]["id"] == transaction.id
    assert queue.json()["summary"]["needs_reconciliation"] == 1
    assert detail.status_code == 200
    assert detail.json()["transaction"]["idempotency_key"] == "web-compliance-parity-1"
    assert "[REDACTED]" in detail.json()["transaction"]["request_payload_json"]
    assert len(detail.json()["events"]) == 4
    assert unconfirmed.status_code == 422
    assert resolved.json()["status"] == "queued"
    assert isolated.status_code == 404


def test_react_traceability_surface_matches_streamlit_labels_tabs_and_drawer():
    source = (ROOT / "frontend" / "src" / "pages" / "CompliancePage.tsx").read_text(encoding="utf-8")
    for label in [
        "TRACEABILITY OPERATIONS · BACKOFFICE", "Queue &amp; Reconciliation", "Needs reconciliation",
        "In flight", "Verified", "Total actions", "Queue view", "Provider", "Inspect transaction",
        "Traceability Operations", "Transaction detail", "Overview", "Attempts", "Lifecycle", "Payloads",
        "SANITIZED REQUEST", "SANITIZED RESPONSE", "Reconciliation action",
        "Reason / reconciliation evidence *", "I reviewed the external state and understand this action is audit logged.",
        "Requeue", "Mark verified", "Cancel action",
    ]:
        assert label in source
    assert "<StreamlitDialog" in source
    assert 'className="modal-backdrop"' not in source
    assert '["Needs reconciliation",["rejected","reconciliation_required"]]' in source
