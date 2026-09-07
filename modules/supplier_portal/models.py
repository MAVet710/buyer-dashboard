"""Durable staged supplier offers linked to the existing partner portal access model."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class SupplierPortalGrant(Base):
    """One-to-one supplier policy for an existing PartnerPortalAccess token."""

    __tablename__ = "supplier_portal_grants"
    __table_args__ = (
        UniqueConstraint("portal_access_id", name="uq_supplier_portal_grant_access"),
        Index("ix_supplier_portal_grant_partner", "organization_id", "partner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    portal_access_id: Mapped[str] = mapped_column(ForeignKey("partner_portal_access.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("commercial_trade_partners.id", ondelete="CASCADE"), nullable=False, index=True)
    permissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupplierOffer(TimestampMixin, Base):
    """Immutable-version supplier submission header; never an inventory or PO mutation."""

    __tablename__ = "supplier_offers"
    __table_args__ = (
        CheckConstraint(
            "status in ('submitted','under_review','accepted','rejected','withdrawn','superseded','expired')",
            name="ck_supplier_offer_status",
        ),
        UniqueConstraint("offer_group_id", "revision", name="uq_supplier_offer_revision"),
        Index("ix_supplier_offer_facility_status", "facility_id", "status", "submitted_at"),
        Index("ix_supplier_offer_partner_group", "partner_id", "offer_group_id", "revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_offer_id: Mapped[str | None] = mapped_column(ForeignKey("supplier_offers.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("commercial_trade_partners.id", ondelete="CASCADE"), nullable=False, index=True)
    portal_access_id: Mapped[str] = mapped_column(ForeignKey("partner_portal_access.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted")
    external_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    promotion_terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupplierOfferLine(Base):
    """One quoted/available supplier item inside a staged offer revision."""

    __tablename__ = "supplier_offer_lines"
    __table_args__ = (
        CheckConstraint("available_quantity >= 0", name="ck_supplier_offer_line_available"),
        CheckConstraint("unit_price >= 0", name="ck_supplier_offer_line_price"),
        CheckConstraint("minimum_order_quantity >= 0", name="ck_supplier_offer_line_minimum"),
        CheckConstraint("sample_status in ('none','offered','requested','approved','sent','received','declined')", name="ck_supplier_offer_line_sample_status"),
        Index("ix_supplier_offer_line_offer", "offer_id", "position"),
        Index("ix_supplier_offer_line_product", "organization_id", "product_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_id: Mapped[str] = mapped_column(ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("coman_products.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_sku: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    strain: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    form: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    package_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    package_size_unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    available_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    availability_unit: Mapped[str] = mapped_column(String(40), nullable=False, default="unit")
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    price_basis: Mapped[str] = mapped_column(String(40), nullable=False, default="unit")
    minimum_order_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    minimum_order_unit: Mapped[str] = mapped_column(String(40), nullable=False, default="unit")
    batch_lot_identifier: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    coa_reference: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    sample_status: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    promotion_terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
