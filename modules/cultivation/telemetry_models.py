"""Provider-neutral environmental evidence, separate from inventory balances."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, new_id, utc_now


class EnvironmentalObservation(Base):
    __tablename__ = "cultivation_environment_observations"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "facility_id", "room_id"],
                             ["cultivation_rooms.organization_id", "cultivation_rooms.facility_id", "cultivation_rooms.id"], ondelete="RESTRICT"),
        UniqueConstraint("organization_id", "facility_id", "room_id", "source", "event_id", "metric", "device_id", name="uq_cultivation_environment_event"),
        CheckConstraint("quality in ('valid','suspect','invalid')", name="ck_environment_quality"),
        Index("ix_environment_room_time", "organization_id", "facility_id", "room_id", "observed_at"),
        Index("ix_environment_stream_time", "room_id", "metric", "source", "device_id", "observed_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    facility_id: Mapped[str] = mapped_column(String(36), nullable=False)
    room_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    device_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EnvironmentalTarget(Base):
    __tablename__ = "cultivation_environment_targets"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "facility_id", "room_id"],
                             ["cultivation_rooms.organization_id", "cultivation_rooms.facility_id", "cultivation_rooms.id"], ondelete="RESTRICT"),
        UniqueConstraint("room_id", "metric", name="uq_environment_target_room_metric"),
        CheckConstraint("minimum IS NULL OR maximum IS NULL OR minimum <= maximum", name="ck_environment_target_range"),
        CheckConstraint("stale_minutes >= 1 AND stale_minutes <= 10080", name="ck_environment_target_stale"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    facility_id: Mapped[str] = mapped_column(String(36), nullable=False)
    room_id: Mapped[str] = mapped_column(String(36), nullable=False)
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    minimum: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum: Mapped[float | None] = mapped_column(Float, nullable=True)
    stale_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
