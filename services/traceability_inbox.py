"""Durable traceability exceptions for the Operations Inbox."""

from __future__ import annotations

from typing import Any, Mapping

from modules.coman.db import create_coman_engine
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.operations_inbox import InboxItem
from services.workspace_navigation import BUYER_WORKSPACE, METRC_INTEGRATIONS_SECTION, RETAIL_OPS


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_traceability_inbox(state: Mapping[str, Any], *, limit: int = 6) -> list[InboxItem]:
    """Read reconciliation-required actions from the durable facility queue.

    Fail closed to an empty list when the database/migration is unavailable so
    Home remains usable during deployment and migration rollouts.
    """

    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    if not organization_id or not facility_id:
        return []

    try:
        repository = TraceabilityBackofficeRepository(create_coman_engine())
        transactions = repository.list_transactions(
            organization_id,
            facility_id,
            statuses=("rejected", "reconciliation_required"),
            limit=max(1, min(int(limit or 6), 20)),
        )
    except Exception:
        return []

    items: list[InboxItem] = []
    for transaction in transactions:
        reconciliation = transaction.status == "reconciliation_required"
        provider = str(transaction.provider or "state system").upper()
        entity = transaction.entity_id or transaction.entity_type
        error = transaction.error_message or transaction.error_code or "External state needs review."
        items.append(
            InboxItem(
                key=f"traceability:{transaction.id}",
                area="Compliance",
                title=(
                    f"{provider} reconciliation required for {entity}"
                    if reconciliation
                    else f"{provider} rejected {transaction.operation_type} for {entity}"
                ),
                detail=error,
                severity="critical" if reconciliation else "high",
                score=125.0 if reconciliation else 116.0,
                route_group=RETAIL_OPS,
                route_workspace=BUYER_WORKSPACE,
                route_section=METRC_INTEGRATIONS_SECTION,
                action_label="Resolve",
                evidence=(
                    f"Status {transaction.status.replace('_', ' ')}",
                    f"Attempts {int(transaction.attempt_count or 0)}",
                    f"Operation {transaction.operation_type}",
                ),
            )
        )
    return items
