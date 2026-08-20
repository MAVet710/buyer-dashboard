"""Provider execution for queued Buyer Dash traceability transactions.

Credentials are supplied only at runtime and are never persisted to the durable
traceability ledger. The processor records sanitized business payloads, immutable
attempt results, and deterministic lifecycle transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from services.metrc_inventory_adjustments import submit_package_adjustment
from .backoffice import TraceabilityBackofficeRepository


TRANSIENT_OR_UNCERTAIN_RESULTS = frozenset(
    {"timeout", "request_error", "rate_limited", "adapter_error"}
)


@dataclass(frozen=True)
class TraceabilityCredentials:
    provider: str
    state: str = ""
    user_api_key: str = ""
    integrator_api_key: str = ""
    license_number: str = ""

    @property
    def configured(self) -> bool:
        provider = str(self.provider or "").strip().casefold()
        if provider == "metrc":
            return bool(
                str(self.state or "").strip()
                and str(self.user_api_key or "").strip()
                and str(self.integrator_api_key or "").strip()
                and str(self.license_number or "").strip()
            )
        return False


def _payload(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _require(value: Any, field: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"Traceability transaction payload is missing {field}.")
    return value


def _submit_metrc(transaction, credentials: TraceabilityCredentials) -> dict[str, Any]:
    if not credentials.configured:
        return {
            "ok": False,
            "status": "missing_credentials",
            "message": "Complete Metrc runtime credentials are required to process this transaction.",
        }
    if transaction.operation_type != "package_adjustment":
        return {
            "ok": False,
            "status": "unsupported_operation",
            "message": f"Metrc provider worker does not support {transaction.operation_type!r} yet.",
        }

    payload = _payload(transaction.request_payload_json)
    try:
        package_label = str(_require(payload.get("package_label"), "package_label"))
        adjustment_type = str(_require(payload.get("adjustment_type"), "adjustment_type"))
        quantity = float(_require(payload.get("quantity"), "quantity"))
        unit = str(_require(payload.get("unit"), "unit"))
        reason = str(_require(payload.get("reason"), "reason"))
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "status": "invalid_payload",
            "message": str(exc),
        }

    return submit_package_adjustment(
        state=credentials.state,
        user_api_key=credentials.user_api_key,
        integrator_api_key=credentials.integrator_api_key,
        license_number=credentials.license_number,
        package_label=package_label,
        adjustment_type=adjustment_type,
        quantity=quantity,
        unit=unit,
        reason=reason,
        reason_note=str(payload.get("reason_note") or ""),
    )


def process_transaction(
    repository: TraceabilityBackofficeRepository,
    *,
    organization_id: str,
    facility_id: str,
    transaction_id: str,
    credentials: TraceabilityCredentials,
    actor: str = "traceability-worker",
):
    """Submit one queued transaction and persist its provider outcome."""

    transaction = repository.get_transaction(
        organization_id,
        facility_id,
        transaction_id,
    )
    if transaction.status != "queued":
        raise ValueError("Only queued traceability transactions can be processed.")
    provider = str(transaction.provider or "").strip().casefold()
    if provider != str(credentials.provider or "").strip().casefold():
        raise ValueError("Runtime credentials do not match the transaction provider.")

    transaction = repository.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status="submitted",
        actor=actor,
        reason="Submitting queued action to external traceability provider.",
        source="worker",
    )

    try:
        if provider == "metrc":
            result = _submit_metrc(transaction, credentials)
        else:
            result = {
                "ok": False,
                "status": "unsupported_provider",
                "message": f"No execution adapter is configured for provider {provider!r}.",
            }
    except Exception as exc:  # defensive boundary around provider adapters
        result = {
            "ok": False,
            "status": "adapter_error",
            "message": f"Traceability adapter failed: {type(exc).__name__}.",
        }

    repository.record_attempt(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        request_payload=_payload(transaction.request_payload_json),
        response_payload=result,
        http_status=result.get("http_status"),
        error_code="" if result.get("ok") else str(result.get("status") or "provider_error"),
        error_message="" if result.get("ok") else str(result.get("message") or "Provider request failed."),
    )

    if result.get("ok"):
        return repository.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction.id,
            new_status="accepted",
            actor=actor,
            reason="External traceability provider accepted the action.",
            source="worker",
            response_payload=result,
            external_reference=str(result.get("external_reference") or ""),
        )

    result_status = str(result.get("status") or "provider_error").strip().casefold()
    target = (
        "reconciliation_required"
        if result_status in TRANSIENT_OR_UNCERTAIN_RESULTS
        else "rejected"
    )
    return repository.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status=target,
        actor=actor,
        reason=str(result.get("message") or "External traceability provider rejected the action."),
        source="worker",
        response_payload=result,
        error_code=result_status,
        error_message=str(result.get("message") or "Provider request failed."),
    )


def process_queued(
    repository: TraceabilityBackofficeRepository,
    *,
    organization_id: str,
    facility_id: str,
    credentials: TraceabilityCredentials,
    actor: str = "traceability-worker",
    limit: int = 25,
) -> list[Any]:
    """Process a bounded batch for one provider/facility runtime credential set."""

    provider = str(credentials.provider or "").strip().casefold()
    queued = repository.list_transactions(
        organization_id,
        facility_id,
        statuses=("queued",),
        provider=provider,
        limit=max(1, min(int(limit or 25), 100)),
    )
    processed = []
    for transaction in reversed(queued):
        processed.append(
            process_transaction(
                repository,
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                credentials=credentials,
                actor=actor,
            )
        )
    return processed
