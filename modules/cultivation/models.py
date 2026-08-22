from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
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
