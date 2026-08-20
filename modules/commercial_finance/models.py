"""Wholesale fulfillment, invoicing, A/R and customer pricing extensions."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class CommercialShipment(TimestampMixin, Base):
    __tablename__ = "commercial_shipments"
    __table_args__ = (
        UniqueConstraint("organization_id", "shipment_number", name="uq_commercial_shipment_org_number"),
        CheckConstraint("status in ('planned','picking','packed','manifested','shipped','delivered','cancelled')", name="ck_commercial_shipment_status"),
        Index("ix_commercial_shipment_facility_status", "facility_id", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    commercial_order_id: Mapped[str] = mapped_column(ForeignKey("commercial_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    shipment_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    manifest_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    carrier: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    tracking_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class CommercialInvoice(TimestampMixin, Base):
    __tablename__ = "commercial_invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_commercial_invoice_org_number"),
        CheckConstraint("status in ('draft','sent','partial','paid','overdue','void')", name="ck_commercial_invoice_status"),
        CheckConstraint("subtotal_usd >= 0 and discount_usd >= 0 and tax_usd >= 0 and total_usd >= 0 and balance_usd >= 0", name="ck_commercial_invoice_amounts"),
        Index("ix_commercial_invoice_facility_status_due", "facility_id", "status", "due_date"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    commercial_order_id: Mapped[str] = mapped_column(ForeignKey("commercial_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("commercial_trade_partners.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    subtotal_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    discount_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tax_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    balance_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class CommercialInvoiceLine(Base):
    __tablename__ = "commercial_invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "position", name="uq_commercial_invoice_line_position"),
        CheckConstraint("quantity > 0 and unit_price_usd >= 0 and line_total_usd >= 0", name="ck_commercial_invoice_line_amounts"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("commercial_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    commercial_order_line_id: Mapped[str | None] = mapped_column(ForeignKey("commercial_order_lines.id", ondelete="SET NULL"), nullable=True, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    line_total_usd: Mapped[float] = mapped_column(Float, nullable=False)


class CommercialPayment(Base):
    __tablename__ = "commercial_payments"
    __table_args__ = (
        CheckConstraint("amount_usd > 0", name="ck_commercial_payment_amount"),
        Index("ix_commercial_payment_invoice_date", "invoice_id", "payment_date"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("commercial_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CustomerPriceRule(TimestampMixin, Base):
    __tablename__ = "customer_price_rules"
    __table_args__ = (
        UniqueConstraint("partner_id", "product_id", name="uq_customer_price_partner_product"),
        CheckConstraint("price_usd >= 0 and discount_pct >= 0 and discount_pct <= 100", name="ck_customer_price_values"),
        Index("ix_customer_price_org_active", "organization_id", "active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("commercial_trade_partners.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True)
    price_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    discount_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
