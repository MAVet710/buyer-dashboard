"""Shared synchronization, reconciliation, and exception semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import Engine, or_, select

from modules.coman.models import utc_now
from .backoffice import TraceabilityBackofficeRepository
from .models import TraceabilityTransaction
from .repository import _clean


EXCEPTION_STATUSES = ("rejected", "reconciliation_required")
MAX_AUTOMATIC_ATTEMPTS = 4


@dataclass(frozen=True)
class FailureClassification:
    code: str
    retryable: bool
    explanation: str
    recommended_action: str


@dataclass(frozen=True)
class ReconciliationClassification:
    state: str
    explanation: str
    recommended_action: str


def machine_status(row: TraceabilityTransaction) -> str:
    if row.resolution_state == "resolved" and row.status in EXCEPTION_STATUSES:
        return "resolved"
    if row.status == "reconciliation_required":
        return "conflict"
    if row.status == "rejected":
        return "failed_retryable" if row.retry_eligible else "failed_permanent"
    if row.status in {"verified", "accepted"}:
        return "succeeded"
    if row.status == "cancelled":
        return "superseded"
    if row.status in {"submitted"}:
        return "processing"
    return "queued"


def classify_failure(*, http_status: int | None = None, error_code: str = "", message: str = "") -> FailureClassification:
    text = f"{error_code} {message}".casefold()
    if http_status == 429 or "rate limit" in text or "too many requests" in text:
        return FailureClassification("rate_limited", True, "Metrc temporarily limited requests.", "Retry after the provider wait period.")
    if http_status in {401, 403} or any(token in text for token in ("credential", "api key", "unauthorized", "permission denied")):
        return FailureClassification("authentication_configuration_failure", False, "The facility credential or provider permission was rejected.", "Review the facility license mapping and Metrc credentials.")
    if http_status is not None and http_status >= 500:
        return FailureClassification("temporary_provider_failure", True, "Metrc returned a temporary service failure.", "Retry safely with the same idempotency key.")
    if any(token in text for token in ("timeout", "timed out", "connection", "network")):
        return FailureClassification("transient_network_failure", True, "The provider result was not received reliably.", "Refresh provider state before retrying the same request.")
    if http_status in {400, 404, 409, 422} or any(token in text for token in ("invalid tag", "validation", "not found", "mapping")):
        return FailureClassification("provider_validation_rejection", False, "Metrc rejected data or could not find a required mapped object.", "Correct the affected mapping or record, then prepare a new retry.")
    return FailureClassification("unknown_provider_response", False, "The provider result could not be classified safely.", "Review provider evidence before taking another action.")


def classify_reconciliation(
    local_state: Mapping[str, Any] | None,
    provider_state: Mapping[str, Any] | None,
    *,
    relationship_fields: Sequence[str] = (),
    stale: bool = False,
) -> ReconciliationClassification:
    local = dict(local_state or {})
    remote = dict(provider_state or {})
    if not local and remote:
        return ReconciliationClassification("missing_locally", "Metrc has this object, but DoobieLogic does not.", "Import or map the Metrc object after review.")
    if local and not remote:
        return ReconciliationClassification("missing_remotely", "DoobieLogic expects this object, but it is not in the synchronized Metrc state.", "Refresh from Metrc and review the object's regulatory identity.")
    if stale:
        return ReconciliationClassification("stale_data", "The comparison uses provider data older than the allowed freshness window.", "Refresh from Metrc before resolving this difference.")
    relationship_mismatches = [field for field in relationship_fields if local.get(field) != remote.get(field)]
    if relationship_mismatches:
        return ReconciliationClassification("relationship_mismatch", f"Related objects differ for: {', '.join(relationship_mismatches)}.", "Open the related Entity 360 records and correct the mapping.")
    changed = sorted(key for key in set(local) | set(remote) if local.get(key) != remote.get(key))
    if changed:
        return ReconciliationClassification("field_mismatch", f"Local and Metrc values differ for: {', '.join(changed)}.", "Review both values and choose the authoritative correction.")
    return ReconciliationClassification("healthy", "DoobieLogic and the synchronized Metrc state agree.", "No action is required.")


class GlobalTraceabilityLedger(TraceabilityBackofficeRepository):
    """One tenant-safe ledger for inbound reads, outbound actions, and recovery."""

    def __init__(self, engine: Engine):
        super().__init__(engine)

    def record_inbound_sync(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        license_number: str,
        resource: str,
        correlation_id: str,
        actor: str,
        record_count: int,
        provider_summary: Mapping[str, Any],
    ) -> TraceabilityTransaction:
        row = self.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type="incremental_sync",
            entity_type="provider_resource",
            entity_id=resource,
            idempotency_key=f"inbound:{environment}:{resource}:{correlation_id}",
            correlation_id=correlation_id,
            actor=actor,
            environment=environment,
            license_number=license_number,
            direction="inbound",
            source="metrc_incremental_sync",
            request_payload={"resource": resource, "mode": "last_modified_delta"},
            reason="Synchronize verified Metrc changes into DoobieLogic.",
        )
        if row.status == "verified":
            return row
        for status in ("validated", "queued", "submitted", "accepted", "verified"):
            row = self.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=row.id,
                new_status=status,
                actor=actor,
                source="provider_sync",
                reason=f"Metrc {resource} delta persisted with {record_count} record(s).",
                response_payload=provider_summary if status == "accepted" else None,
            )
        with self._session_factory.begin() as session:
            stored = self._require_transaction(session, organization_id, facility_id, row.id)
            stored.reconciliation_state = "healthy"
            stored.resolution_state = "resolved"
            stored.resolved_by = actor
            stored.resolved_at = utc_now()
            stored.resolution_note = "Provider delta and local persistence completed."
            session.flush()
            return stored

    def record_inbound_failure(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        license_number: str,
        resource: str,
        correlation_id: str,
        actor: str,
        http_status: int | None,
        error_code: str,
        message: str,
    ) -> TraceabilityTransaction:
        failure = classify_failure(http_status=http_status, error_code=error_code, message=message)
        row = self.create_transaction(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            operation_type="incremental_sync",
            entity_type="provider_resource",
            entity_id=resource,
            idempotency_key=f"inbound:{environment}:{resource}:{correlation_id}",
            correlation_id=correlation_id,
            actor=actor,
            environment=environment,
            license_number=license_number,
            direction="inbound",
            source="metrc_incremental_sync",
            request_payload={"resource": resource, "mode": "last_modified_delta"},
            reason="Synchronize verified Metrc changes into DoobieLogic.",
        )
        if row.status == "requested":
            self.record_attempt(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=row.id,
                http_status=http_status,
                error_code=error_code,
                error_message=message,
            )
            row = self.transition_logged(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=row.id,
                new_status="rejected",
                actor=actor,
                source="provider_sync",
                reason=failure.explanation,
                error_code=error_code or failure.code,
                error_message=message,
                next_attempt_at=(datetime.now(timezone.utc) + timedelta(seconds=30)) if failure.retryable else None,
            )
        with self._session_factory.begin() as session:
            stored = self._require_transaction(session, organization_id, facility_id, row.id)
            stored.error_classification = failure.code
            stored.reconciliation_state = failure.code
            stored.resolution_state = "open"
            stored.retry_eligible = failure.retryable
            session.flush()
            return stored

    def list_exceptions(
        self,
        organization_id: str,
        facility_id: str,
        *,
        environment: str = "",
        entity_type: str = "",
        before: datetime | None = None,
        limit: int = 50,
    ) -> list[TraceabilityTransaction]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self._session_factory() as session:
            statement = select(TraceabilityTransaction).where(
                TraceabilityTransaction.organization_id == organization_id,
                TraceabilityTransaction.facility_id == facility_id,
                TraceabilityTransaction.status.in_(EXCEPTION_STATUSES),
                TraceabilityTransaction.resolution_state != "resolved",
            )
            if environment:
                statement = statement.where(TraceabilityTransaction.environment == _clean(environment).casefold())
            if entity_type:
                statement = statement.where(TraceabilityTransaction.entity_type == _clean(entity_type))
            if before is not None:
                statement = statement.where(TraceabilityTransaction.requested_at < before)
            return list(session.scalars(statement.order_by(TraceabilityTransaction.requested_at.desc()).limit(safe_limit)))

    def entity_history(self, organization_id: str, facility_id: str, entity_type: str, entity_id: str, *, environment: str = "", limit: int = 50) -> list[TraceabilityTransaction]:
        entity_types = {entity_type}
        if entity_type in {"package", "inventory_lot"}:
            entity_types.update({"package", "inventory_lot"})
        with self._session_factory() as session:
            statement = select(TraceabilityTransaction).where(
                TraceabilityTransaction.organization_id == organization_id,
                TraceabilityTransaction.facility_id == facility_id,
                or_(
                    TraceabilityTransaction.entity_type.in_(entity_types) & (TraceabilityTransaction.entity_id == entity_id),
                    TraceabilityTransaction.parent_entity_type.in_(entity_types) & (TraceabilityTransaction.parent_entity_id == entity_id),
                ),
            )
            if environment:
                statement = statement.where(TraceabilityTransaction.environment == _clean(environment).casefold())
            return list(session.scalars(statement.order_by(TraceabilityTransaction.requested_at.desc()).limit(max(1, min(limit, 200)))))

    def resolve_exception(self, organization_id: str, facility_id: str, transaction_id: str, *, actor: str, note: str) -> TraceabilityTransaction:
        if not _clean(note):
            raise ValueError("A resolution note is required.")
        with self._session_factory.begin() as session:
            row = self._require_transaction(session, organization_id, facility_id, transaction_id)
            if row.status not in EXCEPTION_STATUSES:
                raise ValueError("Only an unresolved traceability exception can be resolved.")
            row.resolution_state = "resolved"
            row.resolved_by = _clean(actor)
            row.resolved_at = utc_now()
            row.resolution_note = _clean(note)
            session.flush()
            return row

    def prepare_retry(self, organization_id: str, facility_id: str, transaction_id: str, *, actor: str, reason: str) -> TraceabilityTransaction:
        row = self.get_transaction(organization_id, facility_id, transaction_id)
        if not row.retry_eligible or row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS:
            raise ValueError("This exception cannot be retried safely. Review and correct it first.")
        row = self.requeue_manual(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction_id,
            actor=actor,
            reason=reason,
        )
        with self._session_factory.begin() as session:
            stored = self._require_transaction(session, organization_id, facility_id, row.id)
            stored.resolution_state = "in_progress"
            stored.resolution_note = reason
            stored.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** max(1, stored.attempt_count)))
            session.flush()
            return stored
