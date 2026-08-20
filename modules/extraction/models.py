"""Durable extraction ERP records built on the shared Co-Man SQLAlchemy metadata."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class ExtractionRun(TimestampMixin, Base):
    """One facility-scoped extraction / refinement production run."""

    __tablename__ = "extraction_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "batch_number", name="uq_extraction_run_org_batch"),
        CheckConstraint(
            "status in ('planned','queued','active','hold','qa','complete','cancelled','failed')",
            name="ck_extraction_run_status",
        ),
        CheckConstraint(
            "release_status in ('blocked','pending','approved','rejected')",
            name="ck_extraction_release_status",
        ),
        Index("ix_extraction_runs_facility_status", "facility_id", "status", "created_at"),
        Index("ix_extraction_runs_facility_stage", "facility_id", "current_stage_key", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    production_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_production_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    machine_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_facility_machines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    batch_number: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    current_stage_key: Mapped[str] = mapped_column(String(120), nullable=False, default="intake")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    release_status: Mapped[str] = mapped_column(String(24), nullable=False, default="blocked")
    product_family: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    strain: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    toll_processing: Mapped[bool] = mapped_column(default=False, nullable=False)
    compliance_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="metrc")
    license_number: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    operator: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ExtractionRunInput(TimestampMixin, Base):
    """Reservation/consumption link from a run to the shared inventory lot ledger."""

    __tablename__ = "extraction_run_inputs"
    __table_args__ = (
        UniqueConstraint("run_id", "lot_id", "role", name="uq_extraction_input_run_lot_role"),
        CheckConstraint("planned_quantity >= 0", name="ck_extraction_input_planned"),
        CheckConstraint("reserved_quantity >= 0", name="ck_extraction_input_reserved"),
        CheckConstraint("consumed_quantity >= 0", name="ck_extraction_input_consumed"),
        CheckConstraint("consumed_quantity <= reserved_quantity", name="ck_extraction_input_consume_le_reserve"),
        CheckConstraint(
            "status in ('reserved','partial','consumed','released')",
            name="ck_extraction_input_status",
        ),
        Index("ix_extraction_inputs_run_status", "run_id", "status"),
        Index("ix_extraction_inputs_lot_status", "lot_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="primary_input")
    planned_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reserved_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    consumed_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_cost_snapshot: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    input_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="reserved")
    reserved_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ExtractionStageEvent(Base):
    """Append-only process history; stage updates never overwrite prior measurements."""

    __tablename__ = "extraction_stage_events"
    __table_args__ = (
        CheckConstraint(
            "event_type in ('started','completed','measurement','note','deviation','hold','released')",
            name="ck_extraction_stage_event_type",
        ),
        CheckConstraint("input_weight_g is null or input_weight_g >= 0", name="ck_extraction_stage_input"),
        CheckConstraint("output_weight_g is null or output_weight_g >= 0", name="ck_extraction_stage_output"),
        CheckConstraint("loss_weight_g is null or loss_weight_g >= 0", name="ck_extraction_stage_loss"),
        Index("ix_extraction_stage_run_time", "run_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_key: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    input_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    operator: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    machine_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_facility_machines.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ExtractionRunOutput(TimestampMixin, Base):
    """One WIP/final output created by an extraction run and linked into shared inventory."""

    __tablename__ = "extraction_run_outputs"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="uq_extraction_output_run_position"),
        CheckConstraint("quantity > 0", name="ck_extraction_output_quantity"),
        CheckConstraint(
            "status in ('wip','quarantine','released','waste','destroyed')",
            name="ck_extraction_output_status",
        ),
        CheckConstraint(
            "coa_status in ('not_submitted','pending','passed','failed')",
            name="ck_extraction_output_coa_status",
        ),
        Index("ix_extraction_outputs_run_status", "run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(nullable=False)
    output_label: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="quarantine")
    coa_status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_submitted")
    compliance_package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    output_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ExtractionCostEvent(Base):
    """Append-only run cost ledger used for true COGS and margin analysis."""

    __tablename__ = "extraction_cost_events"
    __table_args__ = (
        CheckConstraint(
            "category in ('material','labor','packaging','processing','overhead','waste','other')",
            name="ck_extraction_cost_category",
        ),
        CheckConstraint("amount_usd >= 0", name="ck_extraction_cost_amount"),
        CheckConstraint("quantity is null or quantity >= 0", name="ck_extraction_cost_quantity"),
        Index("ix_extraction_cost_run_time", "run_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    unit_rate_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ExtractionQAEvent(Base):
    """Append-only QA/release history for a run."""

    __tablename__ = "extraction_qa_events"
    __table_args__ = (
        CheckConstraint(
            "event_type in ('sample_submitted','coa_attached','hold','release','failure','retest','remediation','deviation')",
            name="ck_extraction_qa_event_type",
        ),
        CheckConstraint(
            "result in ('pending','passed','failed','not_applicable')",
            name="ck_extraction_qa_result",
        ),
        Index("ix_extraction_qa_run_time", "run_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    output_id: Mapped[str | None] = mapped_column(
        ForeignKey("extraction_run_outputs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    coa_reference: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    deviation_code: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ExtractionTollJob(TimestampMixin, Base):
    """Commercial terms and SLA state for third-party processing attached to a run."""

    __tablename__ = "extraction_toll_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_extraction_toll_run"),
        CheckConstraint("processing_fee_usd >= 0", name="ck_extraction_toll_fee"),
        CheckConstraint(
            "invoice_status in ('draft','sent','paid','overdue')",
            name="ck_extraction_toll_invoice_status",
        ),
        CheckConstraint(
            "payment_status in ('pending','partial','paid')",
            name="ck_extraction_toll_payment_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("coman_customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    promised_completion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_fee_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    invoice_status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    payment_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    external_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
