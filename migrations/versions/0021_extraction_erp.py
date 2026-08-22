"""Add durable extraction ERP tables.

Revision ID: 0021_extraction_erp
Revises: 0020_product_master
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_extraction_erp"
down_revision = "0020_product_master"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("production_order_id", sa.String(length=36), nullable=True),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("machine_id", sa.String(length=36), nullable=True),
        sa.Column("batch_number", sa.String(length=120), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("workflow_key", sa.String(length=120), nullable=False),
        sa.Column("current_stage_key", sa.String(length=120), nullable=False, server_default="intake"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="planned"),
        sa.Column("release_status", sa.String(length=24), nullable=False, server_default="blocked"),
        sa.Column("product_family", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("strain", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("toll_processing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("compliance_provider", sa.String(length=32), nullable=False, server_default="metrc"),
        sa.Column("license_number", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("operator", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status in ('planned','queued','active','hold','qa','complete','cancelled','failed')", name="ck_extraction_run_status"),
        sa.CheckConstraint("release_status in ('blocked','pending','approved','rejected')", name="ck_extraction_release_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_order_id"], ["coman_production_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["coman_customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["machine_id"], ["coman_facility_machines.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "batch_number", name="uq_extraction_run_org_batch"),
    )
    op.create_index("ix_extraction_runs_organization_id", "extraction_runs", ["organization_id"])
    op.create_index("ix_extraction_runs_facility_id", "extraction_runs", ["facility_id"])
    op.create_index("ix_extraction_runs_production_order_id", "extraction_runs", ["production_order_id"])
    op.create_index("ix_extraction_runs_customer_id", "extraction_runs", ["customer_id"])
    op.create_index("ix_extraction_runs_machine_id", "extraction_runs", ["machine_id"])
    op.create_index("ix_extraction_runs_facility_status", "extraction_runs", ["facility_id", "status", "created_at"])
    op.create_index("ix_extraction_runs_facility_stage", "extraction_runs", ["facility_id", "current_stage_key", "updated_at"])

    op.create_table(
        "extraction_run_inputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("lot_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False, server_default="primary_input"),
        sa.Column("planned_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reserved_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("consumed_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("unit_cost_snapshot", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_reference", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="reserved"),
        sa.Column("reserved_by", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("planned_quantity >= 0", name="ck_extraction_input_planned"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_extraction_input_reserved"),
        sa.CheckConstraint("consumed_quantity >= 0", name="ck_extraction_input_consumed"),
        sa.CheckConstraint("consumed_quantity <= reserved_quantity", name="ck_extraction_input_consume_le_reserve"),
        sa.CheckConstraint("status in ('reserved','partial','consumed','released')", name="ck_extraction_input_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lot_id"], ["coman_inventory_lots.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("run_id", "lot_id", "role", name="uq_extraction_input_run_lot_role"),
    )
    op.create_index("ix_extraction_run_inputs_organization_id", "extraction_run_inputs", ["organization_id"])
    op.create_index("ix_extraction_run_inputs_facility_id", "extraction_run_inputs", ["facility_id"])
    op.create_index("ix_extraction_run_inputs_run_id", "extraction_run_inputs", ["run_id"])
    op.create_index("ix_extraction_run_inputs_lot_id", "extraction_run_inputs", ["lot_id"])
    op.create_index("ix_extraction_inputs_run_status", "extraction_run_inputs", ["run_id", "status"])
    op.create_index("ix_extraction_inputs_lot_status", "extraction_run_inputs", ["lot_id", "status"])

    op.create_table(
        "extraction_stage_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("stage_key", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("input_weight_g", sa.Float(), nullable=True),
        sa.Column("output_weight_g", sa.Float(), nullable=True),
        sa.Column("loss_weight_g", sa.Float(), nullable=True),
        sa.Column("loss_reason", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("operator", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("machine_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("event_type in ('started','completed','measurement','note','deviation','hold','released')", name="ck_extraction_stage_event_type"),
        sa.CheckConstraint("input_weight_g is null or input_weight_g >= 0", name="ck_extraction_stage_input"),
        sa.CheckConstraint("output_weight_g is null or output_weight_g >= 0", name="ck_extraction_stage_output"),
        sa.CheckConstraint("loss_weight_g is null or loss_weight_g >= 0", name="ck_extraction_stage_loss"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["machine_id"], ["coman_facility_machines.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_extraction_stage_events_organization_id", "extraction_stage_events", ["organization_id"])
    op.create_index("ix_extraction_stage_events_facility_id", "extraction_stage_events", ["facility_id"])
    op.create_index("ix_extraction_stage_events_run_id", "extraction_stage_events", ["run_id"])
    op.create_index("ix_extraction_stage_events_machine_id", "extraction_stage_events", ["machine_id"])
    op.create_index("ix_extraction_stage_run_time", "extraction_stage_events", ["run_id", "occurred_at"])

    op.create_table(
        "extraction_run_outputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("lot_id", sa.String(length=36), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("output_label", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="quarantine"),
        sa.Column("coa_status", sa.String(length=24), nullable=False, server_default="not_submitted"),
        sa.Column("compliance_package_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("output_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_extraction_output_quantity"),
        sa.CheckConstraint("status in ('wip','quarantine','released','waste','destroyed')", name="ck_extraction_output_status"),
        sa.CheckConstraint("coa_status in ('not_submitted','pending','passed','failed')", name="ck_extraction_output_coa_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lot_id"], ["coman_inventory_lots.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("run_id", "position", name="uq_extraction_output_run_position"),
    )
    op.create_index("ix_extraction_run_outputs_organization_id", "extraction_run_outputs", ["organization_id"])
    op.create_index("ix_extraction_run_outputs_facility_id", "extraction_run_outputs", ["facility_id"])
    op.create_index("ix_extraction_run_outputs_run_id", "extraction_run_outputs", ["run_id"])
    op.create_index("ix_extraction_run_outputs_product_id", "extraction_run_outputs", ["product_id"])
    op.create_index("ix_extraction_run_outputs_lot_id", "extraction_run_outputs", ["lot_id"])
    op.create_index("ix_extraction_outputs_run_status", "extraction_run_outputs", ["run_id", "status"])

    op.create_table(
        "extraction_cost_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("unit_rate_usd", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("category in ('material','labor','packaging','processing','overhead','waste','other')", name="ck_extraction_cost_category"),
        sa.CheckConstraint("amount_usd >= 0", name="ck_extraction_cost_amount"),
        sa.CheckConstraint("quantity is null or quantity >= 0", name="ck_extraction_cost_quantity"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_extraction_cost_events_organization_id", "extraction_cost_events", ["organization_id"])
    op.create_index("ix_extraction_cost_events_facility_id", "extraction_cost_events", ["facility_id"])
    op.create_index("ix_extraction_cost_events_run_id", "extraction_cost_events", ["run_id"])
    op.create_index("ix_extraction_cost_run_time", "extraction_cost_events", ["run_id", "occurred_at"])

    op.create_table(
        "extraction_qa_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("output_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("coa_reference", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("deviation_code", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("event_type in ('sample_submitted','coa_attached','hold','release','failure','retest','remediation','deviation')", name="ck_extraction_qa_event_type"),
        sa.CheckConstraint("result in ('pending','passed','failed','not_applicable')", name="ck_extraction_qa_result"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_id"], ["extraction_run_outputs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_extraction_qa_events_organization_id", "extraction_qa_events", ["organization_id"])
    op.create_index("ix_extraction_qa_events_facility_id", "extraction_qa_events", ["facility_id"])
    op.create_index("ix_extraction_qa_events_run_id", "extraction_qa_events", ["run_id"])
    op.create_index("ix_extraction_qa_events_output_id", "extraction_qa_events", ["output_id"])
    op.create_index("ix_extraction_qa_run_time", "extraction_qa_events", ["run_id", "occurred_at"])

    op.create_table(
        "extraction_toll_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("promised_completion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_fee_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("invoice_status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("payment_status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("external_reference", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("processing_fee_usd >= 0", name="ck_extraction_toll_fee"),
        sa.CheckConstraint("invoice_status in ('draft','sent','paid','overdue')", name="ck_extraction_toll_invoice_status"),
        sa.CheckConstraint("payment_status in ('pending','partial','paid')", name="ck_extraction_toll_payment_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["coman_customers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("run_id", name="uq_extraction_toll_run"),
    )
    op.create_index("ix_extraction_toll_jobs_organization_id", "extraction_toll_jobs", ["organization_id"])
    op.create_index("ix_extraction_toll_jobs_facility_id", "extraction_toll_jobs", ["facility_id"])
    op.create_index("ix_extraction_toll_jobs_run_id", "extraction_toll_jobs", ["run_id"])
    op.create_index("ix_extraction_toll_jobs_customer_id", "extraction_toll_jobs", ["customer_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "extraction_runs",
            "extraction_run_inputs",
            "extraction_stage_events",
            "extraction_run_outputs",
            "extraction_cost_events",
            "extraction_qa_events",
            "extraction_toll_jobs",
        ):
            op.execute(f"alter table public.{table} enable row level security")


def downgrade() -> None:
    op.drop_table("extraction_toll_jobs")
    op.drop_table("extraction_qa_events")
    op.drop_table("extraction_cost_events")
    op.drop_table("extraction_run_outputs")
    op.drop_table("extraction_stage_events")
    op.drop_table("extraction_run_inputs")
    op.drop_table("extraction_runs")
