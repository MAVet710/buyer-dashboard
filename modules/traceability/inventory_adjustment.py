"""Tracked inventory-adjustment orchestration for Buyer Dash Backoffice."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from modules.coman.db import create_coman_engine
from .backoffice import TraceabilityBackofficeRepository
from .processor import TraceabilityCredentials, process_transaction


LocalApply = Callable[[], tuple[float, str]]


def run_tracked_metrc_adjustment(
    *,
    organization_id: str,
    facility_id: str,
    actor: str,
    credentials: Any,
    package_id: str,
    adjustment_type: str,
    quantity: float,
    unit: str,
    reason: str,
    reason_note: str,
    local_apply: LocalApply,
) -> tuple[float, str, str]:
    """Submit Metrc first, then persist local inventory and verify the action.

    If the provider outcome is not safely accepted, the local inventory callback
    is never executed. If Metrc accepts but local persistence fails, the durable
    transaction is moved to reconciliation_required before the local exception is
    re-raised so the mismatch cannot disappear.
    """

    organization_id = str(organization_id or "").strip()
    facility_id = str(facility_id or "").strip()
    actor = str(actor or "").strip() or "system"
    package_id = str(package_id or "").strip()
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before syncing inventory to Metrc.")
    if not package_id:
        raise ValueError("An External Package ID is required for tracked Metrc adjustment.")
    if credentials is None or not getattr(credentials, "configured", False):
        raise ValueError("A complete Metrc connection is required for tracked inventory adjustment.")

    repository = TraceabilityBackofficeRepository(create_coman_engine())
    transaction = repository.create_transaction(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id=package_id,
        idempotency_key=f"inventory-adjustment:{uuid4()}",
        actor=actor,
        license_number=str(getattr(credentials, "license_number", "") or ""),
        reason=str(reason or "").strip(),
        request_payload={
            "package_label": package_id,
            "adjustment_type": str(adjustment_type or "").strip(),
            "quantity": float(quantity),
            "unit": str(unit or "").strip(),
            "reason": str(reason or "").strip(),
            "reason_note": str(reason_note or "").strip(),
        },
    )
    transaction = repository.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status="validated",
        actor=actor,
        reason="Inventory adjustment inputs and active package context validated.",
        source="inventory",
    )
    transaction = repository.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status="queued",
        actor=actor,
        reason="Inventory adjustment approved for Metrc submission.",
        source="inventory",
    )

    transaction = process_transaction(
        repository,
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        credentials=TraceabilityCredentials(
            provider="metrc",
            state=str(getattr(credentials, "state", "") or ""),
            user_api_key=str(getattr(credentials, "user_api_key", "") or ""),
            integrator_api_key=str(getattr(credentials, "integrator_api_key", "") or ""),
            license_number=str(getattr(credentials, "license_number", "") or ""),
        ),
        actor="traceability-worker",
    )
    if transaction.status != "accepted":
        message = transaction.error_message or (
            "Metrc outcome requires reconciliation."
            if transaction.status == "reconciliation_required"
            else "Metrc rejected the inventory adjustment."
        )
        raise RuntimeError(message)

    try:
        local_delta, local_unit = local_apply()
    except Exception as exc:
        repository.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor=actor,
            reason="Metrc accepted the adjustment but Buyer Dash local inventory persistence failed.",
            source="inventory",
            error_code="local_persistence_failed",
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise

    repository.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status="verified",
        actor=actor,
        reason="Metrc accepted the adjustment and Buyer Dash local inventory persistence completed.",
        source="inventory",
    )
    return local_delta, local_unit, transaction.id
