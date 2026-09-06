"""Tracked inventory-adjustment orchestration for Buyer Dash Backoffice."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from typing import Any

from sqlalchemy import func, select

from modules.coman.db import create_coman_engine
from modules.coman.models import InventoryLot, InventoryTransaction
from modules.regulatory import require_metrc_write_contract
from .backoffice import TraceabilityBackofficeRepository
from .processor import TraceabilityCredentials, process_transaction


LocalApply = Callable[[], tuple[float, str]]
ProviderDispatch = Callable[[str], dict[str, Any]]


def _stable_adjustment_key(
    repository: TraceabilityBackofficeRepository,
    *,
    organization_id: str,
    facility_id: str,
    actor: str,
    package_id: str,
    adjustment_type: str,
    quantity: float,
    unit: str,
    reason: str,
    reason_note: str,
) -> str:
    """Tie idempotency to the exact local pre-state and requested mutation.

    A transport timeout can therefore be retried by the caller without silently
    creating a second provider transaction. Once local inventory changes, the
    pre-state changes too, allowing a genuinely new operator action.
    """

    with repository._session_factory() as session:
        lot = session.scalar(
            select(InventoryLot).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                InventoryLot.compliance_package_id == package_id,
            ).limit(1)
        )
        balance = 0.0
        if lot is not None:
            balance = float(
                session.scalar(
                    select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                        InventoryTransaction.organization_id == organization_id,
                        InventoryTransaction.facility_id == facility_id,
                        InventoryTransaction.lot_id == lot.id,
                    )
                )
                or 0.0
            )
    canonical = json.dumps(
        {
            "organization_id": organization_id,
            "facility_id": facility_id,
            "actor": actor,
            "package_id": package_id,
            "pre_balance": round(balance, 8),
            "adjustment_type": str(adjustment_type or "").strip().casefold(),
            "quantity": round(float(quantity), 8),
            "unit": str(unit or "").strip(),
            "reason": str(reason or "").strip(),
            "reason_note": str(reason_note or "").strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"inventory-adjustment-v2:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


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
    provider_dispatch: ProviderDispatch | None = None,
    repository: TraceabilityBackofficeRepository | None = None,
) -> tuple[float, str, str]:
    """Submit Metrc first, then persist the corresponding local adjustment.

    Trusted web Metrc contexts expose a bound canonical dispatcher after alpha
    mode, connection status, credential scope and facility mapping are verified.
    Tests or other reviewed callers may also pass ``provider_dispatch`` directly.
    The legacy processor fallback remains temporarily for the older Streamlit
    work window and is intentionally isolated for removal under #491.

    Provider acceptance is not provider verification. Canonical-dispatch callers
    therefore remain in ``accepted`` after local persistence and record local
    reconciliation evidence for the later readback step. The legacy fallback
    preserves its historical verified transition until that caller is migrated.
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
    if str(getattr(credentials, "status", "")).casefold() != "connected":
        raise ValueError("Validate the exact facility Metrc connection before a tracked adjustment.")
    if not bool(getattr(credentials, "trusted_mapping", False)):
        raise ValueError("A trusted exact facility/license/jurisdiction/environment mapping is required before a tracked adjustment.")

    state = str(getattr(credentials, "state", "") or "").strip().upper()
    environment = str(getattr(credentials, "environment", "") or "").strip().casefold()
    try:
        require_metrc_write_contract(
            operation_type="package_adjust",
            jurisdiction=state,
            environment=environment,
        )
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    repository = repository or TraceabilityBackofficeRepository(create_coman_engine())
    if provider_dispatch is None:
        candidate = getattr(credentials, "provider_dispatch", None)
        if callable(candidate):
            provider_dispatch = candidate
    idempotency_key = _stable_adjustment_key(
        repository,
        organization_id=organization_id,
        facility_id=facility_id,
        actor=actor,
        package_id=package_id,
        adjustment_type=adjustment_type,
        quantity=quantity,
        unit=unit,
        reason=reason,
        reason_note=reason_note,
    )
    canonical_dispatch = provider_dispatch is not None
    transaction = repository.create_transaction(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        operation_type="package_adjust" if canonical_dispatch else "package_adjustment",
        entity_type="package",
        entity_id=package_id,
        idempotency_key=idempotency_key,
        actor=actor,
        license_number=str(getattr(credentials, "license_number", "") or ""),
        reason=str(reason or "").strip(),
        request_payload={
            # Canonical dispatcher fields.
            "quantity_delta": float(quantity),
            "unit": str(unit or "").strip(),
            "reason": str(reason or "").strip(),
            "reason_note": str(reason_note or "").strip(),
            # Temporary legacy-processor compatibility fields.
            "package_label": package_id,
            "adjustment_type": str(adjustment_type or "").strip(),
            "quantity": float(quantity),
            "environment": environment,
            "jurisdiction_code": state,
        },
    )
    if transaction.status != "requested":
        if transaction.status == "verified":
            raise RuntimeError("This exact adjustment against the same local pre-state was already verified; no duplicate Metrc request was sent.")
        raise RuntimeError(
            f"An identical adjustment already exists in {transaction.status} state. Reconcile that transaction before any repeat provider request."
        )

    transaction = repository.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status="validated",
        actor=actor,
        reason="Inventory adjustment inputs, trusted Metrc mapping, and reviewed write contract validated.",
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

    if provider_dispatch is not None:
        provider_dispatch(transaction.id)
        transaction = repository.get_transaction(organization_id, facility_id, transaction.id)
    else:
        transaction = process_transaction(
            repository,
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            credentials=TraceabilityCredentials(
                provider="metrc",
                state=state,
                user_api_key=str(getattr(credentials, "user_api_key", "") or ""),
                integrator_api_key=str(getattr(credentials, "integrator_api_key", "") or ""),
                license_number=str(getattr(credentials, "license_number", "") or ""),
                environment=environment,
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
            reason="Metrc accepted the adjustment but DoobieLogic local inventory persistence failed.",
            source="inventory",
            error_code="local_persistence_failed",
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise

    if canonical_dispatch:
        repository.record_reconciliation(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            actor=actor,
            local_state={
                "package_id": package_id,
                "inventory_write_applied": True,
                "quantity_delta": float(local_delta),
                "unit": str(local_unit),
            },
            readback_result={"status": "pending"},
            evidence={
                "provider_acceptance_recorded": True,
                "local_persistence_completed": True,
                "verification_pending": True,
            },
            retry_eligible=False,
        )
    else:
        repository.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="verified",
            actor=actor,
            reason="Metrc accepted the adjustment and DoobieLogic local inventory persistence completed.",
            source="inventory",
        )
    return local_delta, local_unit, transaction.id
