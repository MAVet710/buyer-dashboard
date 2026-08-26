"""Durable identity links between DoobieLogic records and accounting providers.

The link ledger makes accounting sync idempotent. Local business records remain the
source of truth inside DoobieLogic; provider IDs and SyncTokens are stored only as
external identity/version metadata.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class AccountingSyncLink(TimestampMixin, Base):
    __tablename__ = "accounting_sync_links"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "organization_id",
            "facility_id",
            "entity_type",
            "internal_id",
            name="uq_accounting_sync_internal",
        ),
        CheckConstraint("provider in ('quickbooks')", name="ck_accounting_sync_provider"),
        CheckConstraint(
            "entity_type in ('customer','vendor','item','invoice','payment','purchase_order','bill')",
            name="ck_accounting_sync_entity_type",
        ),
        CheckConstraint("status in ('synced','failed','stale')", name="ck_accounting_sync_status"),
        Index(
            "ix_accounting_sync_external",
            "organization_id",
            "facility_id",
            "provider",
            "entity_type",
            "external_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="quickbooks")
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    internal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sync_token: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="synced")
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
