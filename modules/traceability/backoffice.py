"""Backoffice traceability operations built on the durable transaction ledger."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from modules.coman.models import utc_now
from .models import TraceabilityStatusEvent, TraceabilityTransaction
from .repository import TraceabilityRepository, VALID_TRANSITIONS, _clean, _payload_json


MANUAL_TRACEABILITY_ROLES = frozenset({"dev", "admin", "supervisor", "qa"})
TERMINAL_STATUSES = frozenset({"verified", "cancelled"})


class TraceabilityBackofficeRepository(TraceabilityRepository):
    """Adds queue browsing and append-only lifecycle evidence for Backoffice."""

    def list_transactions(
        self,
        organization_id: str,
        facility_id: str,
        *,
        statuses: Sequence[str] | None = None,
        provider: str = "",
        limit: int = 250,
    ) -> list[TraceabilityTransaction]:
        safe_limit = max(1, min(int(limit or 250), 1000))
        with self._session_factory() as session:
            statement = select(TraceabilityTransaction).where(
                TraceabilityTransaction.organization_id == organization_id,
                TraceabilityTransaction.facility_id == facility_id,
            )
            normalized_statuses = [
                _clean(status).casefold() for status in (statuses or ()) if _clean(status)
            ]
            if normalized_statuses:
                statement = statement.where(TraceabilityTransaction.status.in_(normalized_statuses))
            normalized_provider = _clean(provider).casefold()
            if normalized_provider:
                statement = statement.where(TraceabilityTransaction.provider == normalized_provider)
            statement = statement.order_by(TraceabilityTransaction.requested_at.desc()).limit(safe_limit)
            return list(session.scalars(statement))

    def summary(self, organization_id: str, facility_id: str) -> dict[str, int]:
        transactions = self.list_transactions(
            organization_id,
            facility_id,
            limit=1000,
        )
        counts = Counter(transaction.status for transaction in transactions)
        counts["total"] = len(transactions)
        counts["needs_reconciliation"] = sum(
            counts.get(status, 0) for status in ("rejected", "reconciliation_required")
        )
        counts["in_flight"] = sum(
            counts.get(status, 0)
            for status in ("requested", "validated", "queued", "submitted", "accepted")
        )
        return dict(counts)

    def list_status_events(
        self,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> list[TraceabilityStatusEvent]:
        with self._session_factory() as session:
            self._require_transaction(session, organization_id, facility_id, transaction_id)
            return list(
                session.scalars(
                    select(TraceabilityStatusEvent)
                    .where(
                        TraceabilityStatusEvent.organization_id == organization_id,
                        TraceabilityStatusEvent.facility_id == facility_id,
                        TraceabilityStatusEvent.transaction_id == transaction_id,
                    )
                    .order_by(TraceabilityStatusEvent.occurred_at)
                )
            )

    def transition_logged(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        new_status: str,
        actor: str,
        reason: str = "",
        source: str = "system",
        external_reference: str = "",
        response_payload: Mapping[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
        next_attempt_at: datetime | None = None,
    ) -> TraceabilityTransaction:
        """Atomically change status and write immutable before/after evidence."""

        target = _clean(new_status).casefold()
        clean_actor = _clean(actor)
        clean_source = _clean(source).casefold() or "system"
        clean_reason = _clean(reason)
        if not clean_actor:
            raise ValueError("An actor is required for traceability lifecycle changes.")
        if clean_source == "manual" and not clean_reason:
            raise ValueError("A reason is required for manual traceability lifecycle changes.")

        with self._session_factory.begin() as session:
            transaction = self._require_transaction(
                session,
                organization_id,
                facility_id,
                transaction_id,
            )
            current = transaction.status
            if target == current:
                return transaction
            allowed = VALID_TRANSITIONS.get(current, frozenset())
            if target not in allowed:
                raise ValueError(f"Traceability transition {current} -> {target} is not allowed.")

            transaction.status = target
            transaction.external_reference = _clean(external_reference) or transaction.external_reference
            if response_payload is not None:
                transaction.response_payload_json = _payload_json(response_payload)
            transaction.error_code = _clean(error_code)
            transaction.error_message = _clean(error_message)
            transaction.next_attempt_at = next_attempt_at
            if target == "submitted" and transaction.submitted_at is None:
                transaction.submitted_at = utc_now()
            if target in TERMINAL_STATUSES:
                transaction.completed_at = utc_now()
            if target in {"validated", "queued", "submitted", "accepted", "verified"}:
                transaction.error_code = ""
                transaction.error_message = ""
            if target in {"queued", "submitted", "accepted", "verified"}:
                transaction.approved_by = clean_actor

            session.add(
                TraceabilityStatusEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    transaction_id=transaction.id,
                    from_status=current,
                    to_status=target,
                    actor=clean_actor,
                    reason=clean_reason,
                    source=clean_source[:32],
                )
            )
            session.flush()
            return transaction

    def requeue_manual(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        actor: str,
        reason: str,
    ) -> TraceabilityTransaction:
        return self.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction_id,
            new_status="queued",
            actor=actor,
            reason=reason,
            source="manual",
        )

    def verify_manual(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        actor: str,
        reason: str,
    ) -> TraceabilityTransaction:
        return self.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction_id,
            new_status="verified",
            actor=actor,
            reason=reason,
            source="manual",
        )

    def cancel_manual(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        actor: str,
        reason: str,
    ) -> TraceabilityTransaction:
        return self.transition_logged(
            organization_id=organization_id,
            facility_id=facility_id,
            transaction_id=transaction_id,
            new_status="cancelled",
            actor=actor,
            reason=reason,
            source="manual",
        )
