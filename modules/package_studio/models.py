"""Durable Package Studio models.

These tables record package transformation intent and lineage without replacing
the existing Co-Man inventory ledger. Inventory balances remain derived from
``coman_inventory_transactions``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


PACKAGE_STUDIO_ACTIONS = (
    "breakdown",
    "pack_down",
    "build_run",
    "multi_build",
    "sample_pull",
    "rework",
    "correction",
)

PACKAGE_STUDIO_PURPOSES = (
    "standard",
    "lab_sample",
    "trade_sample",
    "retail_sample",
    "rework",
    "corrected",
)


class PackageStudioRun(TimestampMixin, Base):
    __tablename__ = "package_studio_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "run_number", name="uq_package_studio_org_run_number"),
        CheckConstraint(
            "action_type in ('breakdown','pack_down','build_run','multi_build','sample_pull','rework','correction')",
            name="ck_package_studio_action_type",
        ),
        CheckConstraint(
            "status in ('draft','reserved','committed','cancelled')",
            name="ck_package_studio_status",
        ),
        CheckConstraint("source_quantity >= 0", name="ck_package_studio_source_qty"),
        CheckConstraint("loss_quantity >= 0", name="ck_package_studio_loss_qty"),
        CheckConstraint(
            "external_sync_status in ('not_requested','pending','synced','failed')",
            name="ck_package_studio_sync_status",
        ),
        Index("ix_package_studio_facility_status", "facility_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_number: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    source_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    loss_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    production_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_production_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    commercial_order_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    external_sync_status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_requested")
    external_sync_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PackageStudioInput(TimestampMixin, Base):
    __tablename__ = "package_studio_inputs"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="uq_package_studio_input_position"),
        CheckConstraint("quantity > 0", name="ck_package_studio_input_qty"),
        Index("ix_package_studio_input_lot", "lot_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("package_studio_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="source")


class PackageStudioOutput(TimestampMixin, Base):
    __tablename__ = "package_studio_outputs"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="uq_package_studio_output_position"),
        UniqueConstraint("facility_id", "lot_code", name="uq_package_studio_output_lot_code"),
        CheckConstraint("inventory_quantity > 0", name="ck_package_studio_output_inventory_qty"),
        CheckConstraint("source_equivalent_quantity >= 0", name="ck_package_studio_output_source_eq_qty"),
        CheckConstraint(
            "purpose in ('standard','lab_sample','trade_sample','retail_sample','rework','corrected')",
            name="ck_package_studio_output_purpose",
        ),
        Index("ix_package_studio_output_lot", "lot_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("package_studio_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    lot_code: Mapped[str] = mapped_column(String(255), nullable=False)
    compliance_package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    inventory_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    inventory_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    source_equivalent_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_equivalent_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    location_code: Mapped[str] = mapped_column(String(120), nullable=False, default="FINISHED-GOODS")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
