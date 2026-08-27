"""Durable hosted-storefront configuration and approval-gated order intake."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class CommerceStorefront(TimestampMixin, Base):
    __tablename__ = "commerce_storefronts"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_commerce_storefront_org_slug"),
        UniqueConstraint("subdomain", name="uq_commerce_storefront_subdomain"),
        Index("ix_commerce_storefront_facility", "facility_id", "published"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    headline: Mapped[str] = mapped_column(String(255), nullable=False, default="Wholesale ordering")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    logo_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    hero_image_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    accent_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#8abf55")
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    order_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class CommerceStorefrontProduct(TimestampMixin, Base):
    __tablename__ = "commerce_storefront_products"
    __table_args__ = (
        UniqueConstraint("storefront_id", "product_id", name="uq_commerce_storefront_product"),
        CheckConstraint("price_usd >= 0", name="ck_commerce_storefront_product_price"),
        CheckConstraint("minimum_quantity > 0", name="ck_commerce_storefront_product_minimum"),
        CheckConstraint("case_quantity > 0", name="ck_commerce_storefront_product_case"),
        Index("ix_commerce_storefront_products_storefront", "storefront_id", "active", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    storefront_id: Mapped[str] = mapped_column(ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True)
    price_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    minimum_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    case_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CommerceStorefrontOrderRequest(TimestampMixin, Base):
    __tablename__ = "commerce_storefront_order_requests"
    __table_args__ = (
        CheckConstraint("status in ('submitted','approved','rejected')", name="ck_commerce_storefront_request_status"),
        Index("ix_commerce_storefront_request_facility_status", "facility_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    storefront_id: Mapped[str] = mapped_column(ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_company: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_license: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    buyer_contact: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    buyer_phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    purchase_order_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    requested_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lines_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    estimated_subtotal: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted")
    partner_id: Mapped[str | None] = mapped_column(ForeignKey("commercial_trade_partners.id", ondelete="SET NULL"), nullable=True, index=True)
    commercial_order_id: Mapped[str | None] = mapped_column(ForeignKey("commercial_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
