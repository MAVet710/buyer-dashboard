from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class CultivationPlant(TimestampMixin, Base):
    __tablename__ = "cultivation_plants"
    __table_args__ = (
        UniqueConstraint("facility_id", "plant_tag", name="uq_cultivation_plant_facility_tag"),
        CheckConstraint("phase in ('clone','seedling','vegetative','flowering','harvested','destroyed')", name="ck_cultivation_plant_phase"),
        Index("ix_cultivation_plants_facility_phase", "facility_id", "phase"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    plant_tag: Mapped[str] = mapped_column(String(255), nullable=False)
    strain_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    room_code: Mapped[str] = mapped_column(String(120), nullable=False, default="UNASSIGNED")
    source_lot_id: Mapped[str | None] = mapped_column(ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True)
    mother_plant_tag: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    planted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class CultivationPlantEvent(Base):
    __tablename__ = "cultivation_plant_events"
    __table_args__ = (Index("ix_cultivation_plant_events_plant_time", "plant_id", "occurred_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_value: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    to_value: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CultivationRoom(TimestampMixin, Base):
    __tablename__ = "cultivation_rooms"
    __table_args__ = (
        UniqueConstraint("facility_id", "room_code", name="uq_cultivation_room_facility_code"),
        CheckConstraint("plant_capacity >= 0", name="ck_cultivation_room_capacity"),
        CheckConstraint("square_feet >= 0", name="ck_cultivation_room_square_feet"),
        CheckConstraint("target_cycle_days >= 0", name="ck_cultivation_room_cycle_days"),
        Index("ix_cultivation_rooms_facility_active", "facility_id", "active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    room_code: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phase: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    plant_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    square_feet: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_cycle_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class CultivationHarvest(TimestampMixin, Base):
    __tablename__ = "cultivation_harvests"
    __table_args__ = (
        UniqueConstraint("facility_id", "harvest_code", name="uq_cultivation_harvest_facility_code"),
        CheckConstraint("status in ('planned','active','drying','finished','cancelled')", name="ck_cultivation_harvest_status"),
        CheckConstraint("wet_weight >= 0", name="ck_cultivation_harvest_wet_weight"),
        CheckConstraint("dry_weight >= 0", name="ck_cultivation_harvest_dry_weight"),
        CheckConstraint("waste_weight >= 0", name="ck_cultivation_harvest_waste_weight"),
        Index("ix_cultivation_harvests_facility_status", "facility_id", "status", "planned_date"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    harvest_code: Mapped[str] = mapped_column(String(160), nullable=False)
    strain_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    room_code: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wet_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dry_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    waste_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(24), nullable=False, default="g")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class CultivationHarvestPlant(Base):
    __tablename__ = "cultivation_harvest_plants"
    __table_args__ = (
        UniqueConstraint("harvest_id", "plant_id", name="uq_cultivation_harvest_plant"),
        Index("ix_cultivation_harvest_plants_plant", "plant_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    harvest_id: Mapped[str] = mapped_column(ForeignKey("cultivation_harvests.id", ondelete="CASCADE"), nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)


class CultivationCostEntry(Base):
    __tablename__ = "cultivation_cost_entries"
    __table_args__ = (
        CheckConstraint("entity_type in ('plant','harvest','room')", name="ck_cultivation_cost_entity_type"),
        CheckConstraint("cost_type in ('labor','material','overhead')", name="ck_cultivation_cost_type"),
        CheckConstraint("quantity >= 0", name="ck_cultivation_cost_quantity"),
        CheckConstraint("unit_cost >= 0", name="ck_cultivation_cost_unit_cost"),
        CheckConstraint("amount >= 0", name="ck_cultivation_cost_amount"),
        Index("ix_cultivation_cost_entries_entity", "organization_id", "facility_id", "entity_type", "entity_id", "occurred_on"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    cost_type: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
