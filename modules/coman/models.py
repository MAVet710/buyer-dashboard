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


class MachineModel(TimestampMixin, Base):
    __tablename__ = "coman_machine_models"
    __table_args__ = (
        UniqueConstraint("manufacturer", "model", name="uq_coman_machine_make_model"),
        CheckConstraint("published_max_rate >= 0", name="ck_coman_machine_rate_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    manufacturer: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    operations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    published_max_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rate_unit: Mapped[str] = mapped_column(String(64), nullable=False, default="units/hour")
    published_min_operators: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_max_operators: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planning_utilization_pct: Mapped[float] = mapped_column(Float, nullable=False, default=65.0)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    source_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FacilityMachine(TimestampMixin, Base):
    __tablename__ = "coman_facility_machines"
    __table_args__ = (
        UniqueConstraint("facility_id", "asset_code", name="uq_coman_facility_machine_asset"),
        CheckConstraint("effective_rate >= 0", name="ck_coman_facility_machine_rate_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    machine_model_id: Mapped[str] = mapped_column(
        ForeignKey("coman_machine_models.id", ondelete="RESTRICT"), nullable=False
    )
    asset_code: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rate_unit: Mapped[str] = mapped_column(String(64), nullable=False, default="units/hour")
    preferred_crew_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cleanup_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class HandLaborArea(TimestampMixin, Base):
    __tablename__ = "coman_hand_labor_areas"
    __table_args__ = (
        UniqueConstraint("facility_id", "name", name="uq_coman_hand_labor_area_name"),
        CheckConstraint("sticker_units_per_person_hour >= 0", name="ck_coman_hand_sticker_rate"),
        CheckConstraint("case_pack_units_per_person_hour >= 0", name="ck_coman_hand_case_rate"),
        CheckConstraint("final_cases_per_person_hour >= 0", name="ck_coman_hand_final_case_rate"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Primary Hand Labor Area")
    default_crew_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sticker_units_per_person_hour: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    case_pack_units_per_person_hour: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_cases_per_person_hour: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cleanup_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CrewAvailability(TimestampMixin, Base):
    __tablename__ = "coman_crew_availability"
    __table_args__ = (
        UniqueConstraint("facility_id", "work_date", "shift_name", name="uq_coman_crew_facility_date_shift"),
        CheckConstraint("available_people >= 0", name="ck_coman_crew_people"),
        CheckConstraint("shift_hours > 0", name="ck_coman_crew_shift_hours"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Day")
    available_people: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shift_hours: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ProductionOrder(TimestampMixin, Base):
    __tablename__ = "coman_production_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "order_number", name="uq_coman_order_org_number"),
        CheckConstraint("requested_units >= 0", name="ck_coman_order_units_nonnegative"),
        CheckConstraint(
            "work_type in ('internal', 'external')", name="ck_coman_order_work_type"
        ),
        Index("ix_coman_orders_facility_status_due", "facility_id", "status", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_customers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    work_type: Mapped[str] = mapped_column(String(16), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    product_format: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_units: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    source_lot_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    material_owner: Mapped[str] = mapped_column(String(255), nullable=False, default="internal")
    packaging_owner: Mapped[str] = mapped_column(String(255), nullable=False, default="internal")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ProductionActual(TimestampMixin, Base):
    __tablename__ = "coman_production_actuals"
    __table_args__ = (
        UniqueConstraint("production_order_id", name="uq_coman_actual_order"),
        CheckConstraint("actual_units >= 0", name="ck_coman_actual_units"),
        CheckConstraint("scrap_units >= 0", name="ck_coman_actual_scrap"),
        CheckConstraint("rework_units >= 0", name="ck_coman_actual_rework"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    production_order_id: Mapped[str] = mapped_column(ForeignKey("coman_production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    actual_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scrap_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rework_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_machine_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actual_labor_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)


class AuditEvent(Base):
    __tablename__ = "coman_audit_events"
    __table_args__ = (Index("ix_coman_audit_entity", "organization_id", "entity_type", "entity_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    changes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AppUser(TimestampMixin, Base):
    __tablename__ = "app_users"
    __table_args__ = (
        CheckConstraint(
            "role in ('dev', 'admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')",
            name="ck_app_users_role",
        ),
        Index("ix_app_users_org_active", "organization_id", "active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="buyer")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")


class AppUserFacilityRole(TimestampMixin, Base):
    __tablename__ = "app_user_facility_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "facility_id", name="uq_app_user_facility"),
        CheckConstraint(
            "role in ('dev', 'admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')",
            name="ck_app_user_facility_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
