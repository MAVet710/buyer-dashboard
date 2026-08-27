"""Generic manufacturing execution extensions built on canonical Co-Man production orders."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class ProductionBomStandard(TimestampMixin, Base):
    """Execution expectations attached 1:1 to a canonical Product BOM version."""

    __tablename__ = "production_bom_standards"
    __table_args__ = (
        UniqueConstraint("bom_id", name="uq_production_bom_standard_bom"),
        CheckConstraint("standard_labor_hours >= 0", name="ck_production_bom_standard_labor"),
        CheckConstraint("standard_machine_hours >= 0", name="ck_production_bom_standard_machine"),
        CheckConstraint("standard_cycle_hours >= 0", name="ck_production_bom_standard_cycle"),
        Index("ix_production_bom_standard_org_bom", "organization_id", "bom_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    bom_id: Mapped[str] = mapped_column(ForeignKey("coman_product_boms.id", ondelete="CASCADE"), nullable=False, index=True)
    standard_labor_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    standard_machine_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    standard_cycle_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    resource_category: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    qa_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    compliance_checkpoint: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ProductionRunEvent(Base):
    __tablename__ = "production_run_events"
    __table_args__ = (
        CheckConstraint("event_type in ('started','completed','measurement','hold','release','rework','waste','note')", name="ck_production_run_event_type"),
        CheckConstraint("quantity is null or quantity >= 0", name="ck_production_run_event_qty"),
        CheckConstraint("waste_quantity is null or waste_quantity >= 0", name="ck_production_run_event_waste"),
        CheckConstraint("labor_hours is null or labor_hours >= 0", name="ck_production_run_event_labor"),
        CheckConstraint("machine_hours is null or machine_hours >= 0", name="ck_production_run_event_machine"),
        Index("ix_production_run_event_order_time", "production_order_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    production_order_id: Mapped[str] = mapped_column(ForeignKey("coman_production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_key: Mapped[str] = mapped_column(String(120), nullable=False, default="execution")
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="unit")
    waste_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    labor_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    machine_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    machine_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facility_machines.id", ondelete="SET NULL"), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProductionRunOutput(TimestampMixin, Base):
    __tablename__ = "production_run_outputs"
    __table_args__ = (
        UniqueConstraint("production_order_id", "position", name="uq_production_run_output_position"),
        CheckConstraint("planned_quantity >= 0", name="ck_production_output_planned"),
        CheckConstraint("actual_quantity >= 0", name="ck_production_output_actual"),
        CheckConstraint("status in ('planned','wip','quarantine','released','rework','waste','destroyed')", name="ck_production_output_status"),
        Index("ix_production_output_order_status", "production_order_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    production_order_id: Mapped[str] = mapped_column(ForeignKey("coman_production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True)
    lot_id: Mapped[str | None] = mapped_column(ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    planned_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actual_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="unit")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ProductionCostEvent(Base):
    __tablename__ = "production_cost_events"
    __table_args__ = (
        CheckConstraint("category in ('material','labor','packaging','machine','overhead','waste','other')", name="ck_production_cost_category"),
        CheckConstraint("amount_usd >= 0", name="ck_production_cost_amount"),
        Index("ix_production_cost_order_time", "production_order_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    production_order_id: Mapped[str] = mapped_column(ForeignKey("coman_production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProductionQAEvent(Base):
    __tablename__ = "production_qa_events"
    __table_args__ = (
        CheckConstraint("event_type in ('hold','sample','pass','fail','release','retest','deviation','remediation')", name="ck_production_qa_event_type"),
        CheckConstraint("result in ('pending','passed','failed','not_applicable')", name="ck_production_qa_result"),
        Index("ix_production_qa_order_time", "production_order_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    production_order_id: Mapped[str] = mapped_column(ForeignKey("coman_production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    output_id: Mapped[str | None] = mapped_column(ForeignKey("production_run_outputs.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    document_reference: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)