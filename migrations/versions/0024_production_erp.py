"""Add generic production execution/QA/COGS tables.

Revision ID: 0024_production_erp
Revises: 0023_switch_center
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_production_erp"
down_revision = "0023_switch_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_run_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("production_order_id", sa.String(36), nullable=False),
        sa.Column("stage_key", sa.String(120), nullable=False, server_default="execution"),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False, server_default="unit"),
        sa.Column("waste_quantity", sa.Float(), nullable=True),
        sa.Column("labor_hours", sa.Float(), nullable=True),
        sa.Column("machine_hours", sa.Float(), nullable=True),
        sa.Column("machine_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("event_type in ('started','completed','measurement','hold','release','rework','waste','note')", name="ck_production_run_event_type"),
        sa.CheckConstraint("quantity is null or quantity >= 0", name="ck_production_run_event_qty"),
        sa.CheckConstraint("waste_quantity is null or waste_quantity >= 0", name="ck_production_run_event_waste"),
        sa.CheckConstraint("labor_hours is null or labor_hours >= 0", name="ck_production_run_event_labor"),
        sa.CheckConstraint("machine_hours is null or machine_hours >= 0", name="ck_production_run_event_machine"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_order_id"], ["coman_production_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["machine_id"], ["coman_facility_machines.id"], ondelete="SET NULL"),
    )
    for col in ("organization_id","facility_id","production_order_id","machine_id"):
        op.create_index(f"ix_production_run_events_{col}", "production_run_events", [col])
    op.create_index("ix_production_run_event_order_time", "production_run_events", ["production_order_id","occurred_at"])

    op.create_table(
        "production_run_outputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("production_order_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("lot_id", sa.String(36), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("planned_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("actual_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(32), nullable=False, server_default="unit"),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("production_order_id","position", name="uq_production_run_output_position"),
        sa.CheckConstraint("planned_quantity >= 0", name="ck_production_output_planned"),
        sa.CheckConstraint("actual_quantity >= 0", name="ck_production_output_actual"),
        sa.CheckConstraint("status in ('planned','wip','quarantine','released','rework','waste','destroyed')", name="ck_production_output_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_order_id"], ["coman_production_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lot_id"], ["coman_inventory_lots.id"], ondelete="SET NULL"),
    )
    for col in ("organization_id","facility_id","production_order_id","product_id","lot_id"):
        op.create_index(f"ix_production_run_outputs_{col}", "production_run_outputs", [col])
    op.create_index("ix_production_output_order_status", "production_run_outputs", ["production_order_id","status"])

    op.create_table(
        "production_cost_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("production_order_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("category in ('material','labor','packaging','machine','overhead','waste','other')", name="ck_production_cost_category"),
        sa.CheckConstraint("amount_usd >= 0", name="ck_production_cost_amount"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_order_id"], ["coman_production_orders.id"], ondelete="CASCADE"),
    )
    for col in ("organization_id","facility_id","production_order_id"):
        op.create_index(f"ix_production_cost_events_{col}", "production_cost_events", [col])
    op.create_index("ix_production_cost_order_time", "production_cost_events", ["production_order_id","occurred_at"])

    op.create_table(
        "production_qa_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("production_order_id", sa.String(36), nullable=False),
        sa.Column("output_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("result", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("document_reference", sa.String(1024), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("event_type in ('hold','sample','pass','fail','release','retest','deviation','remediation')", name="ck_production_qa_event_type"),
        sa.CheckConstraint("result in ('pending','passed','failed','not_applicable')", name="ck_production_qa_result"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_order_id"], ["coman_production_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_id"], ["production_run_outputs.id"], ondelete="SET NULL"),
    )
    for col in ("organization_id","facility_id","production_order_id","output_id"):
        op.create_index(f"ix_production_qa_events_{col}", "production_qa_events", [col])
    op.create_index("ix_production_qa_order_time", "production_qa_events", ["production_order_id","occurred_at"])

    for table in ("production_run_events","production_run_outputs","production_cost_events","production_qa_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("production_qa_events")
    op.drop_table("production_cost_events")
    op.drop_table("production_run_outputs")
    op.drop_table("production_run_events")
