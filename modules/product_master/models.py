"""Durable product-master extension tables.

The canonical product identity remains ``coman_products.id`` so existing Co-Man,
Package Studio, inventory, and commercial workflows keep stable foreign keys.
These tables add richer cannabis identity, vendor relationships, external-system
mappings, aliases, and append-only commercial value history without rewriting the
existing product table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class ProductMasterProfile(TimestampMixin, Base):
    __tablename__ = "product_master_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "product_id", name="uq_product_master_profile_org_product"),
        Index("ix_product_master_profile_brand", "organization_id", "brand"),
        Index("ix_product_master_profile_category", "organization_id", "category"),
    )

    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    subcategory: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    strain: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    manufacturer: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    product_format: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    retail_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    production_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductVendorLink(TimestampMixin, Base):
    __tablename__ = "product_vendor_links"
    __table_args__ = (
        UniqueConstraint("product_id", "partner_id", name="uq_product_vendor_product_partner"),
        CheckConstraint("lead_time_days >= 0", name="ck_product_vendor_lead_time"),
        CheckConstraint("minimum_order_quantity >= 0", name="ck_product_vendor_moq"),
        CheckConstraint("case_pack >= 0", name="ck_product_vendor_case_pack"),
        Index("ix_product_vendor_org_active", "organization_id", "active"),
        Index(
            "uq_product_vendor_active_primary",
            "product_id",
            unique=True,
            postgresql_where=text("is_primary and active"),
            sqlite_where=text("is_primary = 1 and active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    partner_id: Mapped[str] = mapped_column(
        ForeignKey("commercial_trade_partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vendor_sku: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lead_time_days: Mapped[int] = mapped_column(nullable=False, default=0)
    minimum_order_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    case_pack: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductExternalMapping(TimestampMixin, Base):
    __tablename__ = "product_external_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "system_name", "external_id",
            name="uq_product_external_org_system_id",
        ),
        UniqueConstraint(
            "product_id", "system_name", "external_id",
            name="uq_product_external_product_system_id",
        ),
        Index("ix_product_external_lookup", "organization_id", "system_name", "external_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    system_name: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductAlias(TimestampMixin, Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_alias", name="uq_product_alias_org_normalized"),
        Index("ix_product_alias_product", "product_id", "active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="manual")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductValueEvent(Base):
    """Append-only product cost/price history.

    Current unit cost and retail price remain mirrored on ``coman_products`` for
    compatibility; this ledger is the durable history behind those current values.
    """

    __tablename__ = "product_value_events"
    __table_args__ = (
        CheckConstraint(
            "value_type in ('unit_cost','landed_cost','retail_price','wholesale_price')",
            name="ck_product_value_type",
        ),
        CheckConstraint("amount >= 0", name="ck_product_value_amount"),
        Index("ix_product_value_product_time", "product_id", "effective_at"),
        Index("ix_product_value_org_type_time", "organization_id", "value_type", "effective_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    partner_id: Mapped[str | None] = mapped_column(
        ForeignKey("commercial_trade_partners.id", ondelete="SET NULL"), nullable=True, index=True
    )
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    previous_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="manual")
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
