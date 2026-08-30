from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.services.transfer_control import TransferControlService


ROOT = Path(__file__).resolve().parents[1]


def test_outgoing_stage_keeps_human_and_provider_states_distinct():
    stage = TransferControlService._outgoing_stage
    assert stage("proposed", "") == "draft_review"
    assert stage("approved", "") == "approved_not_submitted"
    assert stage("executed", "") == "submitted_unlinked"
    assert stage("executed", "queued") == "queued"
    assert stage("executed", "submitted") == "submitted"
    assert stage("executed", "accepted") == "accepted"
    assert stage("executed", "verified") == "verified"
    assert stage("executed", "reconciliation_required") == "reconciliation_required"


def test_exception_queue_includes_outbound_inbound_and_unrepresented_traceability_failures():
    outgoing = [
        {
            "stage": "reconciliation_required",
            "order_number": "SO-100",
            "title": "Manifest SO-100",
            "mismatch_reason": "Provider package set differs.",
            "error_message": "",
            "proposal_id": "proposal-1",
            "transaction_id": "tx-1",
        }
    ]
    inbound = [
        {
            "status": "processing",
            "manifest": "MAN-200",
            "transfer_id": "in-200",
            "reason": "",
            "preflight_id": "preflight-1",
        },
        {
            "status": "stale",
            "manifest": "MAN-201",
            "transfer_id": "in-201",
            "reason": "Provider snapshot expired.",
            "preflight_id": "preflight-2",
        },
    ]
    traceability = [
        SimpleNamespace(
            id="tx-1",
            status="reconciliation_required",
            entity_id="SO-100",
            mismatch_reason="Provider package set differs.",
            error_message="",
            operation_type="transfer_template_create",
        ),
        SimpleNamespace(
            id="tx-2",
            status="rejected",
            entity_id="PKG-2",
            mismatch_reason="",
            error_message="Provider rejected request.",
            operation_type="package_finish",
        ),
    ]
    rows = TransferControlService._exceptions(
        outgoing=outgoing,
        inbound=inbound,
        traceability=traceability,
    )
    assert {row["reference"] for row in rows} == {"SO-100", "MAN-200", "MAN-201", "PKG-2"}
    assert len([row for row in rows if row.get("transaction_id") == "tx-1"]) == 1
    assert next(row for row in rows if row["reference"] == "MAN-200")["message"].startswith("Local receipt outcome is unknown")


def test_transfer_control_endpoint_is_registered_without_metrc_settings_or_provider_context():
    source = (ROOT / "backend" / "app" / "routers" / "receiving_preflight.py").read_text(encoding="utf-8")
    assert '@router.get("/transfer-control")' in source
    block = source.split('@router.get("/transfer-control")', 1)[1].split('@router.post("/{operation}/inbound', 1)[0]
    assert "TransferControlService(engine).snapshot" in block
    assert "Settings" not in block
    assert "get_settings" not in block
    assert "_metrc_context" not in block


def test_transfer_control_service_never_calls_metrc_or_enables_sandbox_write_promotion():
    source = (ROOT / "backend" / "app" / "services" / "transfer_control.py").read_text(encoding="utf-8")
    assert "requests." not in source
    assert "metrc_client" not in source
    assert '"live_sandbox_promotion_enabled": False' in source
    assert '"provider_network_calls_from_this_view": False' in source
    assert '"inbound_accept_write_enabled": False' in source


def test_wholesale_ops_loads_durable_transfer_control_before_optional_live_metrc():
    source = (ROOT / "frontend" / "src" / "components" / "WholesaleRegulatoryHealth.tsx").read_text(encoding="utf-8")
    assert 'apiGet<TransferControlSnapshot>("/api/v1/inventory/transfer-control"' in source
    assert 'enabled: open' in source
    assert "No live Metrc request has been made from Wholesale Ops." in source
    assert "Transfer exceptions requiring review" in source
    assert "Sales Order → Manifest" in source
    assert "Transfer → Verified Receipt" in source
