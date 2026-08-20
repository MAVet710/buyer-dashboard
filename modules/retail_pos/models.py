"""Durable register, shift, sale-line, and tender models for Buyer Dash POS.

This is the operator-owned transaction ledger needed to replace a third-party
retail POS. Payment processors and state traceability remain adapters around this
ledger rather than the ledger itself.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class RetailRegister(TimestampMixin, Base):
    __tablename__ = "retail_registers"
    __table_args__ = (
        UniqueConstraint("facility_id", "code", name="uq_retail_register_facility_code"),
        Index("ix_retail_register_org_facility_active", "organization_id", "facility_id", "active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)


class RetailShift(TimestampMixin, Base):
    __tablename__ = "retail_shifts"
    __table_args__ = (
        CheckConstraint("status in ('open','closed')", name="ck_retail_shift_status"),
        CheckConstraint("opening_cash >= 0", name="ck_retail_shift_opening_cash"),
        CheckConstraint("closing_cash is null or closing_cash >= 0", name="ck_retail_shift_closing_cash"),
        Index("ix_retail_shift_register_status", "register_id", "status", "opened_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    register_id: Mapped[str] = mapped_column(
        ForeignKey("retail_registers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    opening_cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expected_cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    closing_cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_by: Mapped[str] = mapped_column(String(255), nullable=False)
    closed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RetailTransaction(TimestampMixin, Base):
    __tablename__ = "retail_transactions"
    __table_args__ = (
        UniqueConstraint("organization_id", "transaction_number", name="uq_retail_transaction_org_number"),
        CheckConstraint("transaction_type in ('sale')", name="ck_retail_transaction_type"),
        CheckConstraint("status in ('draft','completed','voided')", name="ck_retail_transaction_status"),
        CheckConstraint("subtotal >= 0", name="ck_retail_transaction_subtotal"),
        CheckConstraint("discount_total >= 0", name="ck_retail_transaction_discount"),
        CheckConstraint("tax_total >= 0", name="ck_retail_transaction_tax"),
        CheckConstraint("total >= 0", name="ck_retail_transaction_total"),
        CheckConstraint("tendered_total >= 0", name="ck_retail_transaction_tendered"),
        CheckConstraint("change_due >= 0", name="ck_retail_transaction_change"),
        Index("ix_retail_tx_facility_status_time", "facility_id", "status", "started_at"),
        Index("ix_retail_tx_shift_time", "shift_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    register_id: Mapped[str] = mapped_column(
        ForeignKey("retail_registers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    shift_id: Mapped[str] = mapped_column(
        ForeignKey("retail_shifts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_number: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(16), nullable=False, default="sale")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    customer_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    subtotal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    discount_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tax_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tendered_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    change_due: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    voided_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    void_reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetailTransactionLine(TimestampMixin, Base):
    __tablename__ = "retail_transaction_lines"
    __table_args__ = (
        UniqueConstraint("transaction_id", "position", name="uq_retail_transaction_line_position"),
        CheckConstraint("quantity > 0", name="ck_retail_line_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_retail_line_unit_price"),
        CheckConstraint("discount_amount >= 0", name="ck_retail_line_discount"),
        CheckConstraint("tax_amount >= 0", name="ck_retail_line_tax"),
        CheckConstraint("line_total >= 0", name="ck_retail_line_total"),
        Index("ix_retail_line_lot_time", "lot_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("retail_transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    sku_snapshot: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    external_package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, nullable=False)


class RetailTender(TimestampMixin, Base):
    __tablename__ = "retail_tenders"
    __table_args__ = (
        UniqueConstraint("transaction_id", "position", name="uq_retail_tender_position"),
        CheckConstraint("tender_type in ('cash','external')", name="ck_retail_tender_type"),
        CheckConstraint("status in ('pending','approved','declined','voided')", name="ck_retail_tender_status"),
        CheckConstraint("amount > 0", name="ck_retail_tender_amount"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("retail_transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    tender_type: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
