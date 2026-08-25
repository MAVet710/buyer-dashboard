from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class IntegrationConfiguration(TimestampMixin, Base):
    __tablename__ = "integration_configurations"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_key", "provider", name="uq_integration_scope_provider"),
        CheckConstraint("scope_type in ('user','facility','platform')", name="ck_integration_scope_type"),
        CheckConstraint(
            "provider in ('metrc','doobie','ai_runtime','spacemail','metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')",
            name="ck_integration_provider",
        ),
        CheckConstraint("status in ('not_connected','configured','connected','failed')", name="ck_integration_status"),
        Index("ix_integration_org_facility", "organization_id", "facility_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(24), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secret_hint: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_connected")
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


SANDBOX_PROVIDER_IDS = (
    "metrc_sandbox",
    "dutchie_sandbox",
    "biotrack_sandbox",
    "quickbooks_sandbox",
)


class IntegrationSyncState(TimestampMixin, Base):
    """Durable cursor and health state for one facility/provider/resource feed."""

    __tablename__ = "integration_sync_states"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "resource",
            name="uq_integration_sync_state_scope",
        ),
        CheckConstraint(
            "provider in ('metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')",
            name="ck_integration_sync_state_provider",
        ),
        CheckConstraint(
            "status in ('idle','running','succeeded','failed')",
            name="ck_integration_sync_state_status",
        ),
        Index("ix_integration_sync_state_facility", "facility_id", "provider", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(24), nullable=False, default="sandbox")
    cursor: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="idle")
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class IntegrationSyncRecord(Base):
    """Immutable raw + normalized provider record staging with deterministic dedupe."""

    __tablename__ = "integration_sync_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "resource",
            "fingerprint",
            name="uq_integration_sync_record_fingerprint",
        ),
        CheckConstraint(
            "provider in ('metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')",
            name="ck_integration_sync_record_provider",
        ),
        CheckConstraint(
            "status in ('accepted','error')",
            name="ck_integration_sync_record_status",
        ),
        Index("ix_integration_sync_record_external", "facility_id", "provider", "resource", "external_id"),
        Index("ix_integration_sync_record_received", "facility_id", "received_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="accepted")
    error_message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class IntegrationSyncAttempt(Base):
    """Append-only execution summary for sandbox feed runs and retries."""

    __tablename__ = "integration_sync_attempts"
    __table_args__ = (
        CheckConstraint(
            "provider in ('metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')",
            name="ck_integration_sync_attempt_provider",
        ),
        CheckConstraint(
            "status in ('running','succeeded','failed')",
            name="ck_integration_sync_attempt_status",
        ),
        Index("ix_integration_sync_attempt_facility", "facility_id", "provider", "started_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    cursor_before: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    cursor_after: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
