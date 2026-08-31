from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class InventoryTransfer(TimestampMixin, Base):
    __tablename__ = "inventory_transfers"
    __table_args__ = (
        UniqueConstraint("organization_id", "manifest_reference", name="uq_inventory_transfer_org_manifest"),
        CheckConstraint(
            "status in ('shipped','partially_received','received','cancelled')",
            name="ck_inventory_transfer_status",
        ),
        CheckConstraint(
            "source_facility_id <> destination_facility_id",
            name="ck_inventory_transfer_distinct_facilities",
        ),
        Index("ix_inventory_transfer_source_status", "source_facility_id", "status", "shipped_at"),
        Index("ix_inventory_transfer_destination_status", "destination_facility_id", "status", "shipped_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_license_number: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    destination_license_number: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    source_facility_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    destination_facility_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    manifest_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    external_transfer_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="shipped")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    shipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InventoryTransferLine(Base):
    __tablename__ = "inventory_transfer_lines"
    __table_args__ = (
        UniqueConstraint("transfer_id", "source_lot_id", name="uq_inventory_transfer_line_source_lot"),
        CheckConstraint("quantity > 0", name="ck_inventory_transfer_line_quantity"),
        CheckConstraint(
            "status in ('shipped','received','cancelled')",
            name="ck_inventory_transfer_line_status",
        ),
        Index("ix_inventory_transfer_line_source_lot", "source_lot_id"),
        Index("ix_inventory_transfer_line_destination_lot", "destination_lot_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transfer_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_transfers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    received_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    source_lot_code: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    destination_lot_code: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    destination_package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_transaction_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_transactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_transactions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="shipped")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
