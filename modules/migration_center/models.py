"""Durable customer migration / switch-center records."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class MigrationBatch(TimestampMixin, Base):
    __tablename__ = "migration_batches"
    __table_args__ = (
        CheckConstraint("source_system in ('dutchie','distru','metrc','spreadsheet','other')", name="ck_migration_batch_source"),
        CheckConstraint("entity_type in ('product','vendor','inventory','sales')", name="ck_migration_batch_entity"),
        CheckConstraint("status in ('staged','review','ready','committed','cancelled','failed')", name="ck_migration_batch_status"),
        Index("ix_migration_batch_facility_status", "facility_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="staged")
    total_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmapped_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MigrationRecord(TimestampMixin, Base):
    __tablename__ = "migration_records"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row_number", name="uq_migration_record_batch_row"),
        CheckConstraint("match_status in ('auto_match','review_required','unmapped','conflict','committed','skipped')", name="ck_migration_record_match_status"),
        CheckConstraint("decision_action in ('pending','accept','create','link','skip')", name="ck_migration_record_decision"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_migration_record_confidence"),
        Index("ix_migration_record_batch_status", "batch_id", "match_status", "source_row_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_external_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    normalized_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    match_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unmapped")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    canonical_entity_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    match_reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    decision_action: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MigrationSalesHistory(Base):
    """Normalized historical sales retained after a competitor cutover."""

    __tablename__ = "migration_sales_history"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_system", "source_external_id", name="uq_migration_sales_source"),
        CheckConstraint("units >= 0", name="ck_migration_sales_units"),
        CheckConstraint("revenue >= 0", name="ck_migration_sales_revenue"),
        Index("ix_migration_sales_product_date", "product_id", "sale_date"),
        Index("ix_migration_sales_facility_date", "facility_id", "sale_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(24), nullable=False)
    source_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("migration_records.id", ondelete="SET NULL"), nullable=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
