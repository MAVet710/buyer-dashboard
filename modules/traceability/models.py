"""Durable state-traceability transaction models.

These tables are provider-neutral infrastructure for Metrc, BioTrack, or future
state systems. They record Buyer Dash intent, validation/submission state,
provider responses, retry/reconciliation state, and immutable attempts. They do
not store API keys or other credentials.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


TRACEABILITY_PROVIDERS = ("metrc", "biotrack", "other")
TRACEABILITY_STATUSES = (
    "requested",
    "validated",
    "queued",
    "submitted",
    "accepted",
    "rejected",
    "verified",
    "reconciliation_required",
    "cancelled",
)


class TraceabilityTransaction(TimestampMixin, Base):
    """One idempotent external compliance action and its lifecycle."""

    __tablename__ = "traceability_transactions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "idempotency_key",
            name="uq_traceability_tx_scope_idempotency",
        ),
        CheckConstraint(
            "provider in ('metrc','biotrack','other')",
            name="ck_traceability_tx_provider",
        ),
        CheckConstraint(
            "status in ('requested','validated','queued','submitted','accepted','rejected','verified','reconciliation_required','cancelled')",
            name="ck_traceability_tx_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_traceability_tx_attempt_count"),
        Index(
            "ix_traceability_tx_facility_status",
            "facility_id",
            "status",
            "requested_at",
        ),
        Index(
            "ix_traceability_tx_entity",
            "organization_id",
            "entity_type",
            "entity_id",
            "requested_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    license_number: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    operation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    request_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    response_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    external_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    error_code: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TraceabilityTransactionAttempt(Base):
    """Immutable record of one provider call attempt for a traceability action."""

    __tablename__ = "traceability_transaction_attempts"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "attempt_number",
            name="uq_traceability_attempt_number",
        ),
        CheckConstraint("attempt_number > 0", name="ck_traceability_attempt_number"),
        Index(
            "ix_traceability_attempt_tx_time",
            "transaction_id",
            "started_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("traceability_transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    response_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
