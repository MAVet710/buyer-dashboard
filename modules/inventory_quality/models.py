"""Canonical lot-level QA and structured COA evidence.

Operational QA systems may keep richer event history, but these tables are the
shared current-state contract used by inventory, transformations, Label Studio,
and commerce.  COA documents preserve the source certificate plus normalized
sample metadata and analyte rows so regulated label values are never flattened
into an opaque potency string.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class CoaDocument(TimestampMixin, Base):
    __tablename__ = "coa_documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "facility_id", "fingerprint", name="uq_coa_document_scope_fingerprint"),
        Index("ix_coa_document_scope_package", "organization_id", "facility_id", "package_id", "status"),
        Index("ix_coa_document_scope_metrc_source", "organization_id", "facility_id", "metrc_source_id"),
        Index("ix_coa_document_lot", "lot_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="library_upload")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="parsed")
    verification_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False, default="application/pdf")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_compressed: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_size: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(96), nullable=False, default="doobielogic-coa")
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")

    product_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    product_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    strain_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    batch_number: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    lab_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    lab_license_number: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    lab_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    metrc_source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    metrc_lab_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    metrc_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    date_tested: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_collected: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_received: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    total_thc_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cbd_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cannabinoids_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_terpenes_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    imported_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CoaAnalyteResult(Base):
    __tablename__ = "coa_analyte_results"
    __table_args__ = (
        Index("ix_coa_analyte_document_order", "coa_document_id", "sort_order"),
        Index("ix_coa_analyte_scope_key", "organization_id", "facility_id", "analyte_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    coa_document_id: Mapped[str] = mapped_column(
        ForeignKey("coa_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis: Mapped[str] = mapped_column(String(96), nullable=False, default="")
    analyte_key: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    units: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    mg_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    lod: Mapped[float | None] = mapped_column(Float, nullable=True)
    loq: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LotQualityEvidence(TimestampMixin, Base):
    __tablename__ = "lot_quality_evidence"
    __table_args__ = (
        Index("ix_lot_quality_scope_state", "organization_id", "facility_id", "lab_testing_state"),
    )

    lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lab_testing_state: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    coa_reference: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    coa_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    coa_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("coa_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    thca_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    tac_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_thc_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cbd_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cannabinoids_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_terpenes_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_source: Mapped[str] = mapped_column(String(96), nullable=False, default="manual")
    inherited_from_lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
