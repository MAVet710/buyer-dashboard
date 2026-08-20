"""Tenant-safe traceability transaction lifecycle and reconciliation repository."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Mapping

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, utc_now
from .models import (
    TRACEABILITY_PROVIDERS,
    TraceabilityTransaction,
    TraceabilityTransactionAttempt,
)


VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "requested": frozenset({"validated", "rejected", "cancelled"}),
    "validated": frozenset({"queued", "rejected", "cancelled"}),
    "queued": frozenset({"submitted", "reconciliation_required", "cancelled"}),
    "submitted": frozenset({"accepted", "rejected", "reconciliation_required"}),
    "accepted": frozenset({"verified", "reconciliation_required"}),
    "rejected": frozenset({"queued", "cancelled"}),
    "reconciliation_required": frozenset({"queued", "verified", "cancelled"}),
    "verified": frozenset(),
    "cancelled": frozenset(),
}

SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "integrator_api_key",
    "user_api_key",
    "secret",
    "password",
    "token",
    "access_token",
    "refresh_token",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _sanitize_payload(value: Any) -> Any:
    """Recursively strip credentials before durable request/response storage."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).strip().casefold() in SENSITIVE_KEYS else _sanitize_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _payload_json(payload: Mapping[str, Any] | None) -> str:
    return json.dumps(
        _sanitize_payload(dict(payload or {})),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


class TraceabilityRepository:
    """Provider-neutral durable queue/reconciliation ledger for state systems."""

    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(
            bind=engine,
            expire_on_commit=False,
            future=True,
        )

    def create_transaction(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        operation_type: str,
        entity_type: str,
        entity_id: str,
        idempotency_key: str,
        actor: str,
        license_number: str = "",
        request_payload: Mapping[str, Any] | None = None,
        reason: str = "",
    ) -> TraceabilityTransaction:
        normalized_provider = _clean(provider).casefold()
        if normalized_provider not in TRACEABILITY_PROVIDERS:
            raise ValueError("Traceability provider must be metrc, biotrack, or other.")
        clean_operation = _clean(operation_type)
        clean_entity_type = _clean(entity_type)
        clean_entity_id = _clean(entity_id)
        clean_idempotency = _clean(idempotency_key)
        clean_actor = _clean(actor)
        if not all((clean_operation, clean_entity_type, clean_entity_id, clean_idempotency, clean_actor)):
            raise ValueError("Operation, entity, idempotency key, and actor are required.")

        with self._session_factory.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("Facility does not belong to the organization.")

            existing = session.scalar(
                select(TraceabilityTransaction).where(
                    TraceabilityTransaction.organization_id == organization_id,
                    TraceabilityTransaction.facility_id == facility_id,
                    TraceabilityTransaction.provider == normalized_provider,
                    TraceabilityTransaction.idempotency_key == clean_idempotency,
                )
            )
            if existing is not None:
                return existing

            transaction = TraceabilityTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                provider=normalized_provider,
                license_number=_clean(license_number),
                operation_type=clean_operation,
                entity_type=clean_entity_type,
                entity_id=clean_entity_id,
                idempotency_key=clean_idempotency,
                request_payload_json=_payload_json(request_payload),
                reason=_clean(reason),
                requested_by=clean_actor,
            )
            session.add(transaction)
            session.flush()
            return transaction

    def get_transaction(
        self,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> TraceabilityTransaction:
        with self._session_factory() as session:
            return self._require_transaction(
                session,
                organization_id,
                facility_id,
                transaction_id,
            )

    def transition(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        new_status: str,
        actor: str = "",
        external_reference: str = "",
        response_payload: Mapping[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
        next_attempt_at: datetime | None = None,
    ) -> TraceabilityTransaction:
        target = _clean(new_status).casefold()
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
            if target in {"verified", "cancelled"}:
                transaction.completed_at = utc_now()
            if target in {"validated", "queued", "submitted", "accepted", "verified"}:
                transaction.error_code = ""
                transaction.error_message = ""
            if actor and target in {"queued", "submitted", "accepted", "verified"}:
                transaction.approved_by = _clean(actor)
            session.flush()
            return transaction

    def record_attempt(
        self,
        *,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
        request_payload: Mapping[str, Any] | None = None,
        response_payload: Mapping[str, Any] | None = None,
        http_status: int | None = None,
        error_code: str = "",
        error_message: str = "",
        completed_at: datetime | None = None,
    ) -> TraceabilityTransactionAttempt:
        with self._session_factory.begin() as session:
            transaction = self._require_transaction(
                session,
                organization_id,
                facility_id,
                transaction_id,
            )
            transaction.attempt_count += 1
            attempt = TraceabilityTransactionAttempt(
                organization_id=organization_id,
                facility_id=facility_id,
                transaction_id=transaction.id,
                attempt_number=transaction.attempt_count,
                request_payload_json=_payload_json(request_payload),
                response_payload_json=_payload_json(response_payload),
                http_status=http_status,
                error_code=_clean(error_code),
                error_message=_clean(error_message),
                completed_at=completed_at or utc_now(),
            )
            session.add(attempt)
            session.flush()
            return attempt

    def list_attempts(
        self,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> list[TraceabilityTransactionAttempt]:
        with self._session_factory() as session:
            self._require_transaction(session, organization_id, facility_id, transaction_id)
            return list(
                session.scalars(
                    select(TraceabilityTransactionAttempt)
                    .where(
                        TraceabilityTransactionAttempt.organization_id == organization_id,
                        TraceabilityTransactionAttempt.facility_id == facility_id,
                        TraceabilityTransactionAttempt.transaction_id == transaction_id,
                    )
                    .order_by(TraceabilityTransactionAttempt.attempt_number)
                )
            )

    def list_reconciliation_queue(
        self,
        organization_id: str,
        facility_id: str,
    ) -> list[TraceabilityTransaction]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(TraceabilityTransaction)
                    .where(
                        TraceabilityTransaction.organization_id == organization_id,
                        TraceabilityTransaction.facility_id == facility_id,
                        TraceabilityTransaction.status.in_(("rejected", "reconciliation_required")),
                    )
                    .order_by(TraceabilityTransaction.requested_at)
                )
            )

    def list_pending(
        self,
        organization_id: str,
        facility_id: str,
    ) -> list[TraceabilityTransaction]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(TraceabilityTransaction)
                    .where(
                        TraceabilityTransaction.organization_id == organization_id,
                        TraceabilityTransaction.facility_id == facility_id,
                        TraceabilityTransaction.status.in_(("requested", "validated", "queued", "submitted", "accepted")),
                    )
                    .order_by(TraceabilityTransaction.requested_at)
                )
            )

    @staticmethod
    def _require_transaction(
        session,
        organization_id: str,
        facility_id: str,
        transaction_id: str,
    ) -> TraceabilityTransaction:
        transaction = session.get(TraceabilityTransaction, transaction_id)
        if (
            transaction is None
            or transaction.organization_id != organization_id
            or transaction.facility_id != facility_id
        ):
            raise ValueError("Traceability transaction was not found in the active facility.")
        return transaction
