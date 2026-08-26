"""Durable identity links between DoobieLogic records and QuickBooks Online.

The link ledger makes accounting sync idempotent. Local business records remain the
source of truth inside DoobieLogic; QuickBooks IDs and SyncTokens are stored only
as provider identity/version metadata.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, new_id, utc_now


class QuickBooksEntityLink(Base):
    __tablename__ = "quickbooks_entity_links"
    __table_args__ = (
        UniqueConstraint(
            "facility_id",
            "local_entity_type",
            "local_entity_id",
            "qbo_entity_type",
            name="uq_qbo_link_local_entity",
        ),
        UniqueConstraint(
            "facility_id",
            "qbo_entity_type",
            "qbo_entity_id",
            name="uq_qbo_link_remote_entity",
        ),
        CheckConstraint(
            "local_entity_type in ('partner','product','invoice','payment','purchase_order','bill')",
            name="ck_qbo_link_local_type",
        ),
        CheckConstraint(
            "qbo_entity_type in ('customer','vendor','item','invoice','payment','purchaseorder','bill')",
            name="ck_qbo_link_remote_type",
        ),
        Index("ix_qbo_link_facility_local", "facility_id", "local_entity_type", "local_entity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    local_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    local_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    qbo_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    qbo_entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sync_token: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_error: Mapped[str] = mapped_column(String(512), nullable=False, default="")
