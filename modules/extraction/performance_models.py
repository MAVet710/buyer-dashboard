"""Durable process-resource usage for Extraction performance intelligence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, new_id, utc_now


class ExtractionResourceEvent(Base):
    """Append-only usage/recovery event for solvents, utilities, gases and consumables."""

    __tablename__ = "extraction_resource_events"
    __table_args__ = (
        CheckConstraint(
            "resource_type in ('solvent','utility','gas','consumable','water','other')",
            name="ck_extraction_resource_type",
        ),
        CheckConstraint("quantity >= 0", name="ck_extraction_resource_quantity"),
        CheckConstraint(
            "recovered_quantity is null or recovered_quantity >= 0",
            name="ck_extraction_resource_recovered_nonnegative",
        ),
        CheckConstraint(
            "recovered_quantity is null or recovered_quantity <= quantity",
            name="ck_extraction_resource_recovered_le_quantity",
        ),
        CheckConstraint("cost_usd >= 0", name="ck_extraction_resource_cost"),
        Index("ix_extraction_resource_run_time", "run_id", "occurred_at"),
        Index("ix_extraction_resource_facility_type", "facility_id", "resource_type", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    resource_type: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    recovered_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
