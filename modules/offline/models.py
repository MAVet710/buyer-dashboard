from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, new_id, utc_now


class OfflineMutationReceipt(Base):
    """Atomic receipt proving an approved offline mutation was applied once."""

    __tablename__ = "offline_mutation_receipts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "endpoint_key",
            "idempotency_key",
            name="uq_offline_mutation_receipt_scope_key",
        ),
        Index(
            "ix_offline_mutation_receipts_scope_time",
            "organization_id",
            "facility_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    endpoint_key: Mapped[str] = mapped_column(String(96), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_entity_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
