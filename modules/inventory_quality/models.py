"""Canonical lot-level QA and COA evidence.

Operational QA systems may keep richer event history, but this table is the
shared current-state contract used by inventory, transformations and commerce.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin


class LotQualityEvidence(TimestampMixin, Base):
    __tablename__ = "lot_quality_evidence"
    __table_args__ = (
        Index("ix_lot_quality_scope_state", "organization_id", "facility_id", "lab_testing_state"),
    )

    lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lab_testing_state: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    coa_reference: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    coa_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    thca_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    tac_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_terpenes_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_source: Mapped[str] = mapped_column(String(96), nullable=False, default="manual")
    inherited_from_lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
