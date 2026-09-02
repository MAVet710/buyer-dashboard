from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class MetrcTagInventory(TimestampMixin, Base):
    """Facility-scoped mirror of Metrc plant/package tags.

    Credentials are never stored here. The table only persists provider identity,
    lifecycle state and the local reservation/consumption relationship needed to
    prevent the same regulatory tag from being promised twice.
    """

    __tablename__ = "regulatory_metrc_tags"
    __table_args__ = (
        UniqueConstraint(
            "facility_id", "environment", "tag_type", "label",
            name="uq_metrc_tag_facility_environment_type_label",
        ),
        CheckConstraint("tag_type in ('plant','package')", name="ck_metrc_tag_type"),
        CheckConstraint("status in ('available','unavailable','reserved','used','voided')", name="ck_metrc_tag_status"),
        Index("ix_metrc_tag_available", "facility_id", "environment", "tag_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    jurisdiction_code: Mapped[str] = mapped_column(String(16), nullable=False)
    license_number: Mapped[str] = mapped_column(String(160), nullable=False)
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    tag_type: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="available")
    reserved_for_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    reserved_for_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CultivationRegulatoryIdentity(TimestampMixin, Base):
    """Separates DoobieLogic's internal plant identity from the Metrc plant tag."""

    __tablename__ = "cultivation_regulatory_identities"
    __table_args__ = (
        UniqueConstraint("plant_id", name="uq_cultivation_regulatory_identity_plant"),
        UniqueConstraint("facility_id", "metrc_plant_tag", name="uq_cultivation_regulatory_metrc_tag"),
        CheckConstraint(
            "origin_type in ('mother','source_package','transfer','beginning_inventory','state_authorized','legacy_demo')",
            name="ck_cultivation_regulatory_origin_type",
        ),
        Index("ix_cultivation_regulatory_identity_facility", "facility_id", "metrc_plant_tag"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("cultivation_plants.id", ondelete="CASCADE"), nullable=False, index=True)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    metrc_plant_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_metrc_plant_tag: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tag_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tag_replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CultivationHarvestPlantWeight(Base):
    __tablename__ = "cultivation_harvest_plant_weights"
    __table_args__ = (
        UniqueConstraint("harvest_id", "plant_id", name="uq_cultivation_harvest_plant_weight"),
        CheckConstraint("wet_weight_g >= 0", name="ck_cultivation_harvest_plant_wet_weight"),
        Index("ix_cultivation_harvest_plant_weight_harvest", "harvest_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    harvest_id: Mapped[str] = mapped_column(ForeignKey("cultivation_harvests.id", ondelete="CASCADE"), nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False, index=True)
    wet_weight_g: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class CultivationWasteRecord(TimestampMixin, Base):
    __tablename__ = "cultivation_waste_records"
    __table_args__ = (
        CheckConstraint("target_type in ('plant','plant_group','harvest')", name="ck_cultivation_waste_target_type"),
        CheckConstraint("weight >= 0", name="ck_cultivation_waste_weight"),
        Index("ix_cultivation_waste_target", "facility_id", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(255), nullable=False)
    material_mixed: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    waste_date: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class CultivationManicureBatch(TimestampMixin, Base):
    __tablename__ = "cultivation_manicure_batches"
    __table_args__ = (
        UniqueConstraint("facility_id", "batch_code", name="uq_cultivation_manicure_batch_code"),
        CheckConstraint("source_phase in ('vegetative','flowering')", name="ck_cultivation_manicure_phase"),
        CheckConstraint("total_weight_g >= 0", name="ck_cultivation_manicure_total_weight"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_code: Mapped[str] = mapped_column(String(120), nullable=False)
    source_phase: Mapped[str] = mapped_column(String(24), nullable=False)
    location: Mapped[str] = mapped_column(String(160), nullable=False)
    manicure_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_weight_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class CultivationManicurePlantWeight(Base):
    __tablename__ = "cultivation_manicure_plant_weights"
    __table_args__ = (
        UniqueConstraint("manicure_batch_id", "plant_id", name="uq_cultivation_manicure_plant"),
        CheckConstraint("weight_g >= 0", name="ck_cultivation_manicure_plant_weight"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    manicure_batch_id: Mapped[str] = mapped_column(ForeignKey("cultivation_manicure_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False, index=True)
    weight_g: Mapped[float] = mapped_column(Float, nullable=False)


class CultivationAdditiveApplication(TimestampMixin, Base):
    __tablename__ = "cultivation_additive_applications"
    __table_args__ = (
        CheckConstraint("target_type in ('plant','plant_group','location')", name="ck_cultivation_additive_target_type"),
        CheckConstraint("amount >= 0", name="ck_cultivation_additive_amount"),
        Index("ix_cultivation_additive_target", "facility_id", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    epa_number: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    supplier: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    active_ingredients: Mapped[str] = mapped_column(Text, nullable=False, default="")
    application_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class CultivationTestSample(TimestampMixin, Base):
    __tablename__ = "cultivation_test_samples"
    __table_args__ = (
        UniqueConstraint("facility_id", "environment", "package_tag", name="uq_cultivation_test_sample_package_tag"),
        CheckConstraint("environment in ('sandbox','production')", name="ck_cultivation_test_sample_environment"),
        CheckConstraint("source_type in ('harvest','package')", name="ck_cultivation_test_sample_source_type"),
        CheckConstraint("quantity > 0", name="ck_cultivation_test_sample_quantity"),
        CheckConstraint("status in ('planned','provider_confirmed','verified','cancelled')", name="ck_cultivation_test_sample_status"),
        Index("ix_cultivation_test_sample_source", "facility_id", "source_type", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    package_tag: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class MetrcTransferControl(TimestampMixin, Base):
    """Regulatory lifecycle overlay for transfers that opt into strict Metrc semantics."""

    __tablename__ = "metrc_transfer_controls"
    __table_args__ = (
        UniqueConstraint("transfer_id", name="uq_metrc_transfer_control_transfer"),
        CheckConstraint("provider_status in ('prepared','departed','partially_received','received','rejected','returned')", name="ck_metrc_transfer_control_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    transfer_id: Mapped[str] = mapped_column(ForeignKey("inventory_transfers.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_transfer_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_status: Mapped[str] = mapped_column(String(32), nullable=False, default="prepared")
    departure_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    departure_confirmed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MetrcTransferLineReturn(TimestampMixin, Base):
    __tablename__ = "metrc_transfer_line_returns"
    __table_args__ = (
        UniqueConstraint("transfer_line_id", name="uq_metrc_transfer_line_return_line"),
        CheckConstraint("status in ('rejected','returning','returned')", name="ck_metrc_transfer_line_return_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    transfer_id: Mapped[str] = mapped_column(ForeignKey("inventory_transfers.id", ondelete="CASCADE"), nullable=False, index=True)
    transfer_line_id: Mapped[str] = mapped_column(ForeignKey("inventory_transfer_lines.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="rejected")
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    rejected_by: Mapped[str] = mapped_column(String(255), nullable=False)
    return_manifest_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
