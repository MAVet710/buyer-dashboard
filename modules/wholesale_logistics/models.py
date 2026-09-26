from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class DispatchRun(TimestampMixin, Base):
    __tablename__ = "wholesale_dispatch_runs"
    __table_args__ = (Index("ix_dispatch_scope_date", "organization_id", "facility_id", "service_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id"), nullable=False)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id"), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    driver_name: Mapped[str | None] = mapped_column(String(255))
    driver_license_number: Mapped[str | None] = mapped_column(String(128))
    vehicle_make: Mapped[str | None] = mapped_column(String(128))
    vehicle_model: Mapped[str | None] = mapped_column(String(128))
    vehicle_license_plate_number: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    __mapper_args__ = {"version_id_col": version}


class DispatchStop(TimestampMixin, Base):
    __tablename__ = "wholesale_dispatch_stops"
    __table_args__ = (
        UniqueConstraint("shipment_id", name="uq_dispatch_shipment"),
        CheckConstraint("status in ('planned','loaded','en_route','arrived','delivered','partial','rejected','returned')", name="ck_dispatch_stop_status"),
        CheckConstraint("sequence > 0", name="ck_dispatch_sequence"),
        CheckConstraint("(latitude is null and longitude is null) or (latitude is not null and longitude is not null and latitude between -90 and 90 and longitude between -180 and 180)", name="ck_dispatch_coordinates"),
        Index("ix_dispatch_stop_run_sequence", "run_id", "sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("wholesale_dispatch_runs.id", ondelete="RESTRICT"), nullable=False)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("commercial_shipments.id", ondelete="RESTRICT"), nullable=False)
    work_item_id: Mapped[str | None] = mapped_column(ForeignKey("doobie_work_items.id", ondelete="SET NULL"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    address_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    contact_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    partner_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    acknowledgment_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
