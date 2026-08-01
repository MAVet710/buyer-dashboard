"""SQLAlchemy models for the first durable Co-Man milestone."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "coman_organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    facilities: Mapped[list["Facility"]] = relationship(back_populates="organization")


class Facility(TimestampMixin, Base):
    __tablename__ = "coman_facilities"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_coman_facility_org_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organization: Mapped[Organization] = relationship(back_populates="facilities")


class Customer(TimestampMixin, Base):
    __tablename__ = "coman_customers"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_coman_customer_org_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_or_registration: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Product(TimestampMixin, Base):
    """Organization product master for cannabis, packaging, WIP, and finished goods."""

    __tablename__ = "coman_products"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_coman_product_org_sku"),
        CheckConstraint("item_type in ('cannabis', 'packaging', 'wip', 'finished_good')", name="ck_coman_product_type"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="unit")
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retail_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    upc: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    external_product_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductBom(TimestampMixin, Base):
    __tablename__ = "coman_product_boms"
    __table_args__ = (UniqueConstraint("organization_id", "output_product_id", "version", name="uq_coman_bom_product_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    output_product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    output_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    expected_loss_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class BomComponent(TimestampMixin, Base):
    __tablename__ = "coman_bom_components"
    __table_args__ = (UniqueConstraint("bom_id", "input_product_id", name="uq_coman_bom_component"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    bom_id: Mapped[str] = mapped_column(ForeignKey("coman_product_boms.id", ondelete="CASCADE"), nullable=False, index=True)
    input_product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    scrap_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class InventoryLot(TimestampMixin, Base):
    __tablename__ = "coman_inventory_lots"
    __table_args__ = (UniqueConstraint("facility_id", "lot_code", name="uq_coman_lot_facility_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True)
    lot_code: Mapped[str] = mapped_column(String(255), nullable=False)
    compliance_package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    external_inventory_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    barcode_value: Mapped[str] = mapped_column(String(512), nullable=False, default="", index=True)
    location_code: Mapped[str] = mapped_column(String(120), nullable=False, default="UNASSIGNED")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiration_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class InventoryTransaction(Base):
    """Append-only inventory ledger; balances are derived from signed quantities."""

    __tablename__ = "coman_inventory_transactions"
    __table_args__ = (Index("ix_coman_inventory_tx_lot_time", "lot_id", "occurred_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    lot_id: Mapped[str] = mapped_column(ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    quantity_delta: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    production_order_id: Mapped[str | None] = mapped_column(ForeignKey("coman_production_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    commercial_order_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    commercial_order_line_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class InventoryAudit(TimestampMixin, Base):
    """Durable physical-count session scoped to one organization facility."""

    __tablename__ = "inventory_audits"
    __table_args__ = (
        UniqueConstraint("organization_id", "audit_number", name="uq_inventory_audit_org_number"),
        CheckConstraint(
            "status in ('draft', 'in_progress', 'completed', 'cancelled')",
            name="ck_inventory_audit_status",
        ),
        CheckConstraint(
            "operation_type in ('retail', 'production')",
            name="ck_inventory_audit_operation_type",
        ),
        Index("ix_inventory_audits_facility_status", "facility_id", "status", "started_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    audit_number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    operation_type: Mapped[str] = mapped_column(String(24), nullable=False, default="production")
    blind_count: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recount_tolerance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scope_label: Mapped[str] = mapped_column(String(255), nullable=False, default="Full facility")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class InventoryAuditLine(TimestampMixin, Base):
    """Expected-versus-physical count for one lot in an inventory audit."""

    __tablename__ = "inventory_audit_lines"
    __table_args__ = (
        UniqueConstraint("audit_id", "lot_id", name="uq_inventory_audit_line_lot"),
        CheckConstraint("expected_quantity >= 0", name="ck_inventory_audit_expected_nonnegative"),
        CheckConstraint(
            "counted_quantity is null or counted_quantity >= 0",
            name="ck_inventory_audit_counted_nonnegative",
        ),
        Index("ix_inventory_audit_lines_audit_counted", "audit_id", "counted_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    audit_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    expected_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    first_count_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    recount_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    counted_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recount_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    counted_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    adjustment_transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )


class InventoryAuditScan(Base):
    """Immutable scan attempt, including unmatched and ambiguous label reads."""

    __tablename__ = "inventory_audit_scans"
    __table_args__ = (
        CheckConstraint(
            "match_status in ('matched', 'unmatched', 'ambiguous')",
            name="ck_inventory_audit_scan_status",
        ),
        CheckConstraint(
            "scan_stage in ('first_count', 'recount')",
            name="ck_inventory_audit_scan_stage",
        ),
        Index("ix_inventory_audit_scans_audit_time", "audit_id", "scanned_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    audit_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audit_line_id: Mapped[str | Noneßö¶‰žËkºwµçU‘m‰½½±t€ôµ…ÁÁ•‘}½±Õµ¸¡	½½±•…¸°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐõQÉÕ”¤4(4(4)±…ÍÌ…¥±¥Ñå5…¡¥¹”¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è4(€€€}}Ñ…‰±•¹…µ•}|€ô€‰½µ…¹}™…¥±¥Ñå}µ…¡¥¹•Ìˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ 4(€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð ‰™…¥±¥Ñå}¥ˆ°€‰…ÍÍ•Ñ}½‘”ˆ°¹…µ”ô‰ÕÅ}½µ…¹}™…¥±¥Ñå}µ…¡¥¹•}…ÍÍ•Ðˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰•™™•Ñ¥Ù•}É…Ñ”€øô€Àˆ°¹…µ”ô‰­}½µ…¹}™…¥±¥Ñå}µ…¡¥¹•}É…Ñ•}¹½¹¹•…Ñ¥Ù”ˆ¤°4(€€€€¤4(4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€™…¥±¥Ñå}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}™…¥±¥Ñ¥•Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€µ…¡¥¹•}µ½‘•±}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}µ…¡¥¹•}µ½‘•±Ì¹¥ˆ°½¹‘•±•Ñ”ô‰IMQI%Pˆ¤°¹Õ±±…‰±”õ…±Í”4(€€€€¤4(€€€…ÍÍ•Ñ}½‘”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€‘¥ÍÁ±…å}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€•™™•Ñ¥Ù•}É…Ñ”è5…ÁÁ•‘m™±½…Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡±½…Ð°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¸À¤4(€€€É…Ñ•}Õ¹¥Ðè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ØÐ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰Õ¹¥ÑÌ½¡½ÕÈˆ¤4(€€€ÁÉ•™•ÉÉ•‘}É•Ý}Í¥é”è5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÄ¤4(€€€Í•ÑÕÁ}µ¥¹ÕÑ•Ìè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€±•…¹ÕÁ}µ¥¹ÕÑ•Ìè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€…Ñ¥Ù”è5…ÁÁ•‘m‰½½±t€ôµ…ÁÁ•‘}½±Õµ¸¡	½½±•…¸°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐõQÉÕ”¤4(4(4)±…ÍÌ!…¹‘1…‰½ÉÉ•„¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è4(€€€}}Ñ…‰±•¹…µ•}|€ô€‰½µ…¹}¡…¹‘}±…‰½É}…É•…Ìˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ 4(€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð ‰™…¥±¥Ñå}¥ˆ°€‰¹…µ”ˆ°¹…µ”ô‰ÕÅ}½µ…¹}¡…¹‘}±…‰½É}…É•…}¹…µ”ˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰ÍÑ¥­•É}Õ¹¥ÑÍ}Á•É}Á•ÉÍ½¹}¡½ÕÈ€øô€Àˆ°¹…µ”ô‰­}½µ…¹}¡…¹‘}ÍÑ¥­•É}É…Ñ”ˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰…Í•}Á…­}Õ¹¥ÑÍ}Á•É}Á•ÉÍ½¹}¡½ÕÈ€øô€Àˆ°¹…µ”ô‰­}½µ…¹}¡…¹‘}…Í•}É…Ñ”ˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰™¥¹…±}…Í•Í}Á•É}Á•ÉÍ½¹}¡½ÕÈ€øô€Àˆ°¹…µ”ô‰­}½µ…¹}¡…¹‘}™¥¹…±}…Í•}É…Ñ”ˆ¤°4(€€€€¤4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€™…¥±¥Ñå}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡½É•¥¹-•ä ‰½µ…¹}™…¥±¥Ñ¥•Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰AÉ¥µ…Éä!…¹1…‰½ÈÉ•„ˆ¤4(€€€‘•™…Õ±Ñ}É•Ý}Í¥é”è5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÄ¤4(€€€ÍÑ¥­•É}Õ¹¥ÑÍ}Á•É}Á•ÉÍ½¹}¡½ÕÈè5…ÁÁ•‘m™±½…Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡±½…Ð°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¸À¤4(€€€…Í•}Á…­}Õ¹¥ÑÍ}Á•É}Á•ÉÍ½¹}¡½ÕÈè5…ÁÁ•‘m™±½…Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡±½…Ð°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¸À¤4(€€€™¥¹…±}…Í•Í}Á•É}Á•ÉÍ½¹}¡½ÕÈè5…ÁÁ•‘m™±½…Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡±½…Ð°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¸À¤4(€€€Í•ÑÕÁ}µ¥¹ÕÑ•Ìè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€±•…¹ÕÁ}µ¥¹ÕÑ•Ìè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€…Ñ¥Ù”è5…ÁÁ•‘m‰½½±t€ôµ…ÁÁ•‘}½±Õµ¸¡	½½±•…¸°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐõQÉÕ”¤4(4(4)±…ÍÌÉ•ÝÙ…¥±…‰¥±¥Ñä¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è4(€€€}}Ñ…‰±•¹…µ•}|€ô€‰½µ…¹}É•Ý}…Ù…¥±…‰¥±¥Ñäˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ 4(€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð ‰™…¥±¥Ñå}¥ˆ°€‰Ý½É­}‘…Ñ”ˆ°€‰Í¡¥™Ñ}¹…µ”ˆ°¹…µ”ô‰ÕÅ}½µ…¹}É•Ý}™…¥±¥Ñå}‘…Ñ•}Í¡¥™Ðˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰…Ù…¥±…‰±•}Á•½Á±”€øô€Àˆ°¹…µ”ô‰­}½µ…¹}É•Ý}Á•½Á±”ˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰Í¡¥™Ñ}¡½ÕÉÌ€ø€Àˆ°¹…µ”ô‰­}½µ…¹}É•Ý}Í¡¥™Ñ}¡½ÕÉÌˆ¤°4(€€€€¤4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€™…¥±¥Ñå}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡½É•¥¹-•ä ‰½µ…¹}™…¥±¥Ñ¥•Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€Ý½É­}‘…Ñ”è5…ÁÁ•‘m‘…Ñ•t€ôµ…ÁÁ•‘}½±Õµ¸¡…Ñ”°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€Í¡¥™Ñ}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰…äˆ¤4(€€€…Ù…¥±…‰±•}Á•½Á±”è5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€Í¡¥™Ñ}¡½ÕÉÌè5…ÁÁ•‘m™±½…Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡±½…Ð°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôà¸À¤4(€€€¹½Ñ•Ìè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡Q•áÐ°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤4(€€€ÕÁ‘…Ñ•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(4(4)±…ÍÌAÉ½‘ÕÑ¥½¹=É‘•È¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è4(€€€}}Ñ…‰±•¹…µ•}|€ô€‰½µ…¹}ÁÉ½‘ÕÑ¥½¹}½É‘•ÉÌˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ 4(€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð ‰½É…¹¥é…Ñ¥½¹}¥ˆ°€‰½É‘•É}¹Õµ‰•Èˆ°¹…µ”ô‰ÕÅ}½µ…¹}½É‘•É}½É}¹Õµ‰•Èˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰É•ÅÕ•ÍÑ•‘}Õ¹¥ÑÌ€øô€Àˆ°¹…µ”ô‰­}½µ…¹}½É‘•É}Õ¹¥ÑÍ}¹½¹¹•…Ñ¥Ù”ˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð 4(€€€€€€€€€€€€‰Ý½É­}ÑåÁ”¥¸€ ¥¹Ñ•É¹…°œ°€•áÑ•É¹…°œ¤ˆ°¹…µ”ô‰­}½µ…¹}½É‘•É}Ý½É­}ÑåÁ”ˆ4(€€€€€€€€¤°4(€€€€€€€%¹‘•à ‰¥á}½µ…¹}½É‘•ÉÍ}™…¥±¥Ñå}ÍÑ…ÑÕÍ}‘Õ”ˆ°€‰™…¥±¥Ñå}¥ˆ°€‰ÍÑ…ÑÕÌˆ°€‰‘Õ•}…Ðˆ¤°4(€€€€¤4(4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€™…¥±¥Ñå}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}™…¥±¥Ñ¥•Ì¹¥ˆ°½¹‘•±•Ñ”ô‰IMQI%Pˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€ÕÍÑ½µ•É}¥è5…ÁÁ•‘mÍÑÈð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}ÕÍÑ½µ•ÉÌ¹¥ˆ°½¹‘•±•Ñ”ô‰IMQI%Pˆ¤°¹Õ±±…‰±”õQÉÕ”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€½É‘•É}¹Õµ‰•Èè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ØÐ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€Ý½É­}ÑåÁ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄØ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€ÁÉ½‘ÕÑ}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€Í­Ôè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤4(€€€ÁÉ½‘ÕÑ}™½Éµ…Ðè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€É•ÅÕ•ÍÑ•‘}Õ¹¥ÑÌè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”¤4(€€€‘Õ•}…Ðè5…ÁÁ•‘m‘…Ñ•Ñ¥µ”ð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸¡…Ñ•Q¥µ”¡Ñ¥µ•é½¹”õQÉÕ”¤°¹Õ±±…‰±”õQÉÕ”¤4(€€€ÁÉ¥½É¥Ñäè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌÈ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰¹½Éµ…°ˆ¤4(€€€ÍÑ…ÑÕÌè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌÈ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰‘É…™Ðˆ¤4(€€€Í½ÕÉ•}±½Ñ}É•™•É•¹”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤4(€€€µ…Ñ•É¥…±}½Ý¹•Èè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰¥¹Ñ•É¹…°ˆ¤4(€€€Á…­…¥¹}½Ý¹•Èè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰¥¹Ñ•É¹…°ˆ¤4(€€€¹½Ñ•Ìè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡Q•áÐ°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤4(€€€É•…Ñ•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€ÕÁ‘…Ñ•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(4(4)±…ÍÌAÉ½‘ÕÑ¥½¹ÑÕ…°¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è4(€€€}}Ñ…‰±•¹…µ•}|€ô€‰½µ…¹}ÁÉ½‘ÕÑ¥½¹}…ÑÕ…±Ìˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ 4(€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð ‰ÁÉ½‘ÕÑ¥½¹}½É‘•É}¥ˆ°¹…µ”ô‰ÕÅ}½µ…¹}…ÑÕ…±}½É‘•Èˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰…ÑÕ…±}Õ¹¥ÑÌ€øô€Àˆ°¹…µ”ô‰­}½µ…¹}…ÑÕ…±}Õ¹¥ÑÌˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰ÍÉ…Á}Õ¹¥ÑÌ€øô€Àˆ°¹…µ”ô‰­}½µ…¹}…ÑÕ…±}ÍÉ…Àˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð ‰É•Ý½É­}Õ¹¥ÑÌ€øô€Àˆ°¹…µ”ô‰­}½µ…¹}…ÑÕ…±}É•Ý½É¬ˆ¤°4(€€€€¤4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€™…¥±¥Ñå}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡½É•¥¹-•ä ‰½µ…¹}™…¥±¥Ñ¥•Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€ÁÉ½‘ÕÑ¥½¹}½É‘•É}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡½É•¥¹-•ä ‰½µ…¹}ÁÉ½‘ÕÑ¥½¹}½É‘•ÉÌ¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”¤4(€€€…ÑÕ…±}Õ¹¥ÑÌè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€ÍÉ…Á}Õ¹¥ÑÌè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€É•Ý½É­}Õ¹¥ÑÌè5…ÁÁ•‘m¥¹Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡%¹Ñ••È°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¤4(€€€…ÑÕ…±}µ…¡¥¹•}¡½ÕÉÌè5…ÁÁ•‘m™±½…Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡±½…Ð°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¸À¤4(€€€…ÑÕ…±}±…‰½É}¡½ÕÉÌè5…ÁÁ•‘m™±½…Ñt€ôµ…ÁÁ•‘}½±Õµ¸¡±½…Ð°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐôÀ¸À¤4(€€€½µÁ±•Ñ•‘}…Ðè5…ÁÁ•‘m‘…Ñ•Ñ¥µ”ð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸¡…Ñ•Q¥µ”¡Ñ¥µ•é½¹”õQÉÕ”¤°¹Õ±±…‰±”õQÉÕ”¤4(€€€¹½Ñ•Ìè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡Q•áÐ°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤4(€€€É•½É‘•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(4(4)±…ÍÌÕ‘¥ÑÙ•¹Ð¡	…Í”¤è(€€€}}Ñ…‰±•¹…µ•}|€ô€‰½µ…¹}…Õ‘¥Ñ}•Ù•¹ÑÌˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€¡%¹‘•à ‰¥á}½µ…¹}…Õ‘¥Ñ}•¹Ñ¥Ñäˆ°€‰½É…¹¥é…Ñ¥½¹}¥ˆ°€‰•¹Ñ¥Ñå}ÑåÁ”ˆ°€‰•¹Ñ¥Ñå}¥ˆ¤°¤4(4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€™…¥±¥Ñå}¥è5…ÁÁ•‘mÍÑÈð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}™…¥±¥Ñ¥•Ì¹¥ˆ°½¹‘•±•Ñ”ô‰MP9U10ˆ¤°¹Õ±±…‰±”õQÉÕ”4(€€€€¤4(€€€•¹Ñ¥Ñå}ÑåÁ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€•¹Ñ¥Ñå}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€…Ñ¥½¸è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€…Ñ½Èè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€¡…¹•Í}©Í½¸è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡Q•áÐ°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰íôˆ¤4(€€€½ÕÉÉ•‘}…Ðè5…ÁÁ•‘m‘…Ñ•Ñ¥µ•t€ôµ…ÁÁ•‘}½±Õµ¸¡…Ñ•Q¥µ”¡Ñ¥µ•é½¹”õQÉÕ”¤°‘•™…Õ±ÐõÕÑ}¹½Ü°¹Õ±±…‰±”õ…±Í”¤(()±…ÍÌ…Ñ…±½9½µ•¹±…ÑÕÉ•%Ñ•´¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è(€€€€ˆˆ‰=¹”½É…¹¥é…Ñ¥½¸ÌÕÑ¡¥”…Ñ…±½œ…Ì¥ÑÌ…ÁÁÉ½Ù•¹…µ¥¹œÍ½ÕÉ”¸ˆˆˆ((€€€}}Ñ…‰±•¹…µ•}|€ô€‰…Ñ…±½}¹½µ•¹±…ÑÕÉ•}¥Ñ•µÌˆ(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ (€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð (€€€€€€€€€€€€‰½É…¹¥é…Ñ¥½¹}¥ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}ÍåÍÑ•´ˆ°(€€€€€€€€€€€€‰¹½Éµ…±¥é•‘}¹…µ”ˆ°(€€€€€€€€€€€¹…µ”ô‰ÕÅ}…Ñ…±½}¹½µ•¹±…ÑÕÉ•}½É}Í½ÕÉ•}¹…µ”ˆ°(€€€€€€€€¤°(€€€€€€€%¹‘•à ‰¥á}…Ñ…±½}¹½µ•¹±…ÑÕÉ•}½É}…Ñ¥Ù”ˆ°€‰½É…¹¥é…Ñ¥½¹}¥ˆ°€‰…Ñ¥Ù”ˆ¤°(€€€€¤((€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ (€€€€€€€½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”(€€€€¤(€€€Í½ÕÉ•}ÍåÍÑ•´è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌÈ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰‘ÕÑ¡¥”ˆ¤(€€€…¹½¹¥…±}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÔÄÈ¤°¹Õ±±…‰±”õ…±Í”¤(€€€¹½Éµ…±¥é•‘}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÔÄÈ¤°¹Õ±±…‰±”õ…±Í”¤(€€€Í­Ôè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤(€€€…Ñ•½Éäè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤(€€€‰É…¹è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤(€€€…Ñ¥Ù”è5…ÁÁ•‘m‰½½±t€ôµ…ÁÁ•‘}½±Õµ¸¡	½½±•…¸°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐõQÉÕ”¤(€€€¥µÁ½ÉÑ•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰ÍåÍÑ•´ˆ¤(()±…ÍÌ…Ñ…±½9½µ•¹±…ÑÕÉ•5…ÁÁ¥¹œ¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è(€€€€ˆˆ‰½¹™¥Éµ•5QIÍ½ÕÉ”¹…µ”Ñ¼½É…¹¥é…Ñ¥½¸…Ñ…±½œµ¹…µ”µ…ÁÁ¥¹œ¸ˆˆˆ((€€€}}Ñ…‰±•¹…µ•}|€ô€‰…Ñ…±½}¹½µ•¹±…ÑÕÉ•}µ…ÁÁ¥¹Ìˆ(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ (€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð (€€€€€€€€€€€€‰½É…¹¥é…Ñ¥½¹}¥ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}ÍåÍÑ•´ˆ°(€€€€€€€€€€€€‰Í½ÕÉ•}¹½Éµ…±¥é•‘}¹…µ”ˆ°(€€€€€€€€€€€¹…µ”ô‰ÕÅ}…Ñ…±½}µ…ÁÁ¥¹}½É}Í½ÕÉ•}¹…µ”ˆ°(€€€€€€€€¤°(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð (€€€€€€€€€€€€‰ÍÑ…ÑÕÌ¥¸€ ½¹™¥Éµ•œ°€É•Ñ¥É•œ¤ˆ°(€€€€€€€€€€€¹…µ”ô‰­}…Ñ…±½}µ…ÁÁ¥¹}ÍÑ…ÑÕÌˆ°(€€€€€€€€¤°(€€€€€€€%¹‘•à ‰¥á}…Ñ…±½}µ…ÁÁ¥¹}½É}ÍÑ…ÑÕÌˆ°€‰½É…¹¥é…Ñ¥½¹}¥ˆ°€‰ÍÑ…ÑÕÌˆ¤°(€€€€¤((€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ (€€€€€€€½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”(€€€€¤(€€€…Ñ…±½}¥Ñ•µ}¥è5…ÁÁ•‘mÍÑÈð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸ (€€€€€€€½É•¥¹-•ä ‰…Ñ…±½}¹½µ•¹±…ÑÕÉ•}¥Ñ•µÌ¹¥ˆ°½¹‘•±•Ñ”ô‰MP9U10ˆ¤°¹Õ±±…‰±”õQÉÕ”°¥¹‘•àõQÉÕ”(€€€€¤(€€€Í½ÕÉ•}ÍåÍÑ•´è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌÈ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰µ•ÑÉŒˆ¤(€€€Í½ÕÉ•}¥Ñ•µ}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÔÄÈ¤°¹Õ±±…‰±”õ…±Í”¤(€€€Í½ÕÉ•}¹½Éµ…±¥é•‘}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÔÄÈ¤°¹Õ±±…‰±”õ…±Í”¤(€€€½ÉÉ•Ñ}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÔÄÈ¤°¹Õ±±…‰±”õ…±Í”¤(€€€ÍÑ…ÑÕÌè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÐ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰½¹™¥Éµ•ˆ¤(€€€½¹™¥Éµ•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤(€€€½¹™¥Éµ•‘}…Ðè5…ÁÁ•‘m‘…Ñ•Ñ¥µ•t€ôµ…ÁÁ•‘}½±Õµ¸¡…Ñ•Q¥µ”¡Ñ¥µ•é½¹”õQÉÕ”¤°‘•™…Õ±ÐõÕÑ}¹½Ü°¹Õ±±…‰±”õ…±Í”¤(()±…ÍÌÁÁUÍ•È¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è(€€€}}Ñ…‰±•¹…µ•}|€ô€‰…ÁÁ}ÕÍ•ÉÌˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ 4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð 4(€€€€€€€€€€€€‰É½±”¥¸€ ‘•Øœ°€…‘µ¥¸œ°€‰Õå•Èœ°€Á±…¹¹•Èœ°€ÍÕÁ•ÉÙ¥Í½Èœ°€½Á•É…Ñ½Èœ°€Å„œ°€É•…‘}½¹±äœ¤ˆ°4(€€€€€€€€€€€¹…µ”ô‰­}…ÁÁ}ÕÍ•ÉÍ}É½±”ˆ°4(€€€€€€€€¤°4(€€€€€€€%¹‘•à ‰¥á}…ÁÁ}ÕÍ•ÉÍ}½É}…Ñ¥Ù”ˆ°€‰½É…¹¥é…Ñ¥½¹}¥ˆ°€‰…Ñ¥Ù”ˆ¤°4(€€€€¤4(4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÈð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰MP9U10ˆ¤°¹Õ±±…‰±”õQÉÕ”4(€€€€¤4(€€€ÕÍ•É¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€¹½Éµ…±¥é•‘}ÕÍ•É¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÄÈÀ¤°¹Õ±±…‰±”õ…±Í”°Õ¹¥ÅÕ”õQÉÕ”¤4(€€€‘¥ÍÁ±…å}¹…µ”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤4(€€€•µ…¥°è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌÈÀ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðôˆˆ¤4(€€€Á…ÍÍÝ½É‘}¡…Í è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”¤4(€€€É½±”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌÈ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰‰Õå•Èˆ¤4(€€€…Ñ¥Ù”è5…ÁÁ•‘m‰½½±t€ôµ…ÁÁ•‘}½±Õµ¸¡	½½±•…¸°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐõQÉÕ”¤4(€€€µÕÍÑ}¡…¹•}Á…ÍÍÝ½Éè5…ÁÁ•‘m‰½½±t€ôµ…ÁÁ•‘}½±Õµ¸¡	½½±•…¸°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±ÐõQÉÕ”¤4(€€€±…ÍÑ}±½¥¹}…Ðè5…ÁÁ•‘m‘…Ñ•Ñ¥µ”ð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸¡…Ñ•Q¥µ”¡Ñ¥µ•é½¹”õQÉÕ”¤°¹Õ±±…‰±”õQÉÕ”¤4(€€€Á…ÍÍÝ½É‘}¡…¹•‘}…Ðè5…ÁÁ•‘m‘…Ñ•Ñ¥µ”ð9½¹•t€ôµ…ÁÁ•‘}½±Õµ¸¡…Ñ•Q¥µ”¡Ñ¥µ•é½¹”õQÉÕ”¤°¹Õ±±…‰±”õQÉÕ”¤4(€€€É•…Ñ•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰ÍåÍÑ•´ˆ¤4(€€€ÕÁ‘…Ñ•‘}‰äè5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÈÔÔ¤°¹Õ±±…‰±”õ…±Í”°‘•™…Õ±Ðô‰ÍåÍÑ•´ˆ¤4(4(4)±…ÍÌÁÁUÍ•É…¥±¥ÑåI½±”¡Q¥µ•ÍÑ…µÁ5¥á¥¸°	…Í”¤è4(€€€}}Ñ…‰±•¹…µ•}|€ô€‰…ÁÁ}ÕÍ•É}™…¥±¥Ñå}É½±•Ìˆ4(€€€}}Ñ…‰±•}…ÉÍ}|€ô€ 4(€€€€€€€U¹¥ÅÕ•½¹ÍÑÉ…¥¹Ð ‰ÕÍ•É}¥ˆ°€‰™…¥±¥Ñå}¥ˆ°¹…µ”ô‰ÕÅ}…ÁÁ}ÕÍ•É}™…¥±¥Ñäˆ¤°4(€€€€€€€¡•­½¹ÍÑÉ…¥¹Ð 4(€€€€€€€€€€€€‰É½±”¥¸€ ‘•Øœ°€…‘µ¥¸œ°€‰Õå•Èœ°€Á±…¹¹•Èœ°€ÍÕÁ•ÉÙ¥Í½Èœ°€½Á•É…Ñ½Èœ°€Å„œ°€É•…‘}½¹±äœ¤ˆ°4(€€€€€€€€€€€¹…µ”ô‰­}…ÁÁ}ÕÍ•É}™…¥±¥Ñå}É½±”ˆ°4(€€€€€€€€¤°4(€€€€¤4(4(€€€¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌØ¤°ÁÉ¥µ…Éå}­•äõQÉÕ”°‘•™…Õ±Ðõ¹•Ý}¥¤4(€€€ÕÍ•É}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰…ÁÁ}ÕÍ•ÉÌ¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€½É…¹¥é…Ñ¥½¹}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}½É…¹¥é…Ñ¥½¹Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€™…¥±¥Ñå}¥è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸ 4(€€€€€€€½É•¥¹-•ä ‰½µ…¹}™…¥±¥Ñ¥•Ì¹¥ˆ°½¹‘•±•Ñ”ô‰Mˆ¤°¹Õ±±…‰±”õ…±Í”°¥¹‘•àõQÉÕ”4(€€€€¤4(€€€É½±”è5…ÁÁ•‘mÍÑÉt€ôµ…ÁÁ•‘}½±Õµ¸¡MÑÉ¥¹œ ÌÈ¤°¹Õ±±…‰±”õ…±Í”¤4