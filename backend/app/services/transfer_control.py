from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.doobie_actions.models import ActionExecution, ActionProposal
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.models import ReceivingPreflight


OUTGOING_ACTION_TYPE = "prepare_transfer_manifest"
EXCEPTION_TRACEABILITY_STATUSES = {"rejected", "reconciliation_required"}
OPEN_TRACEABILITY_STATUSES = {"requested", "validated", "queued", "submitted", "accepted"}
OPEN_PREFLIGHT_STATUSES = {"prepared", "processing", "stale"}


def _json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class TransferControlService:
    """Facility-scoped transfer operations view built only from durable local state.

    This service intentionally performs no provider network calls and enables no
    Metrc writes. It joins the existing manifest proposal/action lifecycle,
    traceability transaction ledger, and inbound receiving preflight records so
    operators can see the end-to-end transfer state and exception queue while
    sandbox write promotion remains independently gated.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.traceability = TraceabilityBackofficeRepository(engine)

    def snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        outgoing = self._outgoing(organization_id, facility_id)
        inbound = self._inbound(organization_id, facility_id)
        traceability = self.traceability.list_transactions(
            organization_id,
            facility_id,
            limit=500,
        )
        exceptions = self._exceptions(outgoing=outgoing, inbound=inbound, traceability=traceability)
        trace_counts = Counter(row.status for row in traceability)
        return {
            "metrics": {
                "outgoing_open": sum(row["stage"] not in {"verified", "cancelled", "rejected"} for row in outgoing),
                "inbound_open": sum(row["status"] in OPEN_PREFLIGHT_STATUSES for row in inbound),
                "provider_in_flight": sum(trace_counts.get(status, 0) for status in OPEN_TRACEABILITY_STATUSES),
                "exceptions": len(exceptions),
                "verified": trace_counts.get("verified", 0),
            },
            "outgoing": outgoing,
            "inbound": inbound,
            "exceptions": exceptions,
            "policy": {
                "live_sandbox_promotion_enabled": False,
                "provider_network_calls_from_this_view": False,
                "inbound_accept_write_enabled": False,
                "message": (
                    "Transfer Control is a durable operational view. Live Metrc package-write promotion remains disabled until "
                    "sandbox credentials and provider readback evidence are available. Existing approved manifest submission "
                    "workflows remain separately gated and are not invoked by this endpoint."
                ),
            },
        }

    def _outgoing(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            proposals = list(
                session.scalars(
                    select(ActionProposal)
                    .where(
                        ActionProposal.organization_id == organization_id,
                        ActionProposal.facility_id == facility_id,
                        ActionProposal.action_type == OUTGOING_ACTION_TYPE,
                    )
                    .order_by(ActionProposal.created_at.desc())
                    .limit(250)
                )
            )
            executions = list(
                session.scalars(
                    select(ActionExecution)
                    .where(
                        ActionExecution.organization_id == organization_id,
                        ActionExecution.facility_id == facility_id,
                        ActionExecution.proposal_id.in_([row.id for row in proposals] or ["__none__"]),
                    )
                    .order_by(ActionExecution.started_at.desc())
                )
            )
        latest_execution: dict[str, ActionExecution] = {}
        for execution in executions:
            latest_execution.setdefault(execution.proposal_id, execution)

        rows: list[dict[str, Any]] = []
        for proposal in proposals:
            preview = _json_dict(proposal.preview_json)
            payload = _json_dict(proposal.payload_json)
            execution = latest_execution.get(proposal.id)
            execution_result = _json_dict(execution.result_json) if execution is not None else {}
            transaction_id = str(execution_result.get("transaction_id") or "").strip()
            transaction = None
            if transaction_id:
                try:
                    transaction = self.traceability.get_transaction(organization_id, facility_id, transaction_id)
                except ValueError:
                    transaction = None
            stage = self._outgoing_stage(proposal.status, transaction.status if transaction is not None else "")
            request_payload = payload.get("request_payload") if isinstance(payload.get("request_payload"), dict) else {}
            commercial_order_id = str(request_payload.get("commercial_order_id") or preview.get("sales_order", {}).get("id") or "")
            customer = preview.get("customer") if isinstance(preview.get("customer"), dict) else {}
            packages = preview.get("packages") if isinstance(preview.get("packages"), list) else []
            rows.append(
                {
                    "proposal_id": proposal.id,
                    "title": proposal.title,
                    "stage": stage,
                    "proposal_status": proposal.status,
                    "traceability_status": transaction.status if transaction is not None else "",
                    "transaction_id": transaction_id,
                    "external_reference": transaction.external_reference if transaction is not None else "",
                    "commercial_order_id": commercial_order_id,
                    "order_number": str((preview.get("sales_order") or {}).get("order_number") or ""),
                    "customer": str(customer.get("name") or ""),
                    "customer_license": str(customer.get("license") or ""),
                    "package_count": len(packages),
                    "departure": str(preview.get("estimated_departure") or ""),
                    "arrival": str(preview.get("estimated_arrival") or ""),
                    "route": str(preview.get("route") or ""),
                    "financial_impact_usd": float(proposal.financial_impact_usd or 0),
                    "created_at": _iso(proposal.created_at),
                    "approved_at": _iso(proposal.approved_at),
                    "error_message": transaction.error_message if transaction is not None else (execution.error_message if execution is not None else ""),
                    "mismatch_reason": transaction.mismatch_reason if transaction is not None else "",
                }
            )
        return rows

    def _inbound(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(ReceivingPreflight)
                    .where(
                        ReceivingPreflight.organization_id == organization_id,
                        ReceivingPreflight.facility_id == facility_id,
                    )
                    .order_by(ReceivingPreflight.created_at.desc())
                    .limit(250)
                )
            )
        output: list[dict[str, Any]] = []
        for row in rows:
            snapshot = _json_dict(row.snapshot_json)
            packages = snapshot.get("packages") if isinstance(snapshot.get("packages"), list) else []
            expires_at = _aware(row.expires_at)
            is_expired = bool(expires_at is not None and expires_at <= now and row.status == "prepared")
            output.append(
                {
                    "preflight_id": row.id,
                    "transfer_id": row.transfer_id,
                    "operation": row.operation,
                    "status": "stale" if is_expired else row.status,
                    "provider": row.provider,
                    "jurisdiction": row.jurisdiction,
                    "environment": row.environment,
                    "manifest": str(snapshot.get("manifest") or ""),
                    "vendor": str(snapshot.get("vendor") or ""),
                    "vendor_license": str(snapshot.get("vendor_license") or ""),
                    "package_count": len(packages),
                    "expires_at": _iso(row.expires_at),
                    "consumed_at": _iso(row.consumed_at),
                    "received_count": len(_json_list(row.local_result_json)) if row.status == "consumed" else 0,
                    "reason": row.reason,
                }
            )
        return output

    @staticmethod
    def _outgoing_stage(proposal_status: str, traceability_status: str) -> str:
        proposal = str(proposal_status or "").casefold()
        traceability = str(traceability_status or "").casefold()
        if traceability in {"verified", "cancelled", "rejected", "reconciliation_required"}:
            return traceability
        if traceability in {"submitted", "accepted"}:
            return traceability
        if traceability in {"requested", "validated", "queued"}:
            return "queued"
        return {
            "proposed": "draft_review",
            "approved": "approved_not_submitted",
            "executing": "submitting",
            "executed": "submitted_unlinked",
            "failed": "failed",
            "rejected": "rejected",
            "expired": "expired",
        }.get(proposal, proposal or "unknown")

    @staticmethod
    def _exceptions(*, outgoing: list[dict[str, Any]], inbound: list[dict[str, Any]], traceability: list[Any]) -> list[dict[str, Any]]:
        exceptions: list[dict[str, Any]] = []
        for row in outgoing:
            if row["stage"] in {"rejected", "reconciliation_required", "failed", "expired"}:
                exceptions.append(
                    {
                        "kind": "outgoing",
                        "reference": row["order_number"] or row["title"],
                        "status": row["stage"],
                        "message": row["mismatch_reason"] or row["error_message"] or "Outgoing transfer requires operator review.",
                        "proposal_id": row["proposal_id"],
                        "transaction_id": row["transaction_id"],
                    }
                )
        for row in inbound:
            if row["status"] in {"processing", "stale", "cancelled"}:
                default = {
                    "processing": "Local receipt outcome is unknown; reconcile before retrying.",
                    "stale": "Provider confirmation is stale; refresh the inbound transfer before posting.",
                    "cancelled": "Receiving preflight was cancelled and cannot be reused.",
                }[row["status"]]
                exceptions.append(
                    {
                        "kind": "inbound",
                        "reference": row["manifest"] or row["transfer_id"],
                        "status": row["status"],
                        "message": row["reason"] or default,
                        "preflight_id": row["preflight_id"],
                    }
                )
        represented_transactions = {row.get("transaction_id") for row in exceptions if row.get("transaction_id")}
        for transaction in traceability:
            if transaction.status not in EXCEPTION_TRACEABILITY_STATUSES or transaction.id in represented_transactions:
                continue
            exceptions.append(
                {
                    "kind": "traceability",
                    "reference": transaction.entity_id or transaction.id,
                    "status": transaction.status,
                    "message": transaction.mismatch_reason or transaction.error_message or "Provider reconciliation is required.",
                    "transaction_id": transaction.id,
                    "operation_type": transaction.operation_type,
                }
            )
        return exceptions
