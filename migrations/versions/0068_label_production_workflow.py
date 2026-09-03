"""Add inventory-driven Label Studio production runs and audit events.

Revision ID: 0068_label_production_workflow
Revises: 0067_post_harvest_workflow
"""

import sqlalchemy as sa
from alembic import op

revision = "0068_label_production_workflow"
down_revision = "0067_post_harvest_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "label_production_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("expected_material_quantity", sa.Float(), nullable=False),
        sa.Column("expected_material_unit", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("metrc_package_tag", sa.String(length=255), nullable=True),
        sa.Column("label_snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("printed_by", sa.String(length=255), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tag_assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_label_production_run_quantity_positive"),
        sa.CheckConstraint("expected_material_quantity >= 0", name="ck_label_production_expected_nonnegative"),
        sa.CheckConstraint(
            "status in ('draft','validated','tagged','printed','applied','released','fulfilled','archived')",
            name="ck_label_production_run_status",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "metrc_package_tag", name="uq_label_production_org_metrc_tag"),
    )
    op.create_index("ix_label_production_facility_status", "label_production_runs", ["facility_id", "status"], unique=False)
    op.create_index(op.f("ix_label_production_runs_organization_id"), "label_production_runs", ["organization_id"], unique=False)
    op.create_index(op.f("ix_label_production_runs_facility_id"), "label_production_runs", ["facility_id"], unique=False)
    op.create_index(op.f("ix_label_production_runs_product_id"), "label_production_runs", ["product_id"], unique=False)

    op.create_table(
        "label_production_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_lot_id", sa.String(length=36), nullable=False),
        sa.Column("planned_quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.CheckConstraint("planned_quantity >= 0", name="ck_label_production_source_nonnegative"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["label_production_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_lot_id"], ["coman_inventory_lots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "source_lot_id", name="uq_label_production_run_source"),
    )
    op.create_index(op.f("ix_label_production_sources_organization_id"), "label_production_sources", ["organization_id"], unique=False)
    op.create_index(op.f("ix_label_production_sources_facility_id"), "label_production_sources", ["facility_id"], unique=False)
    op.create_index(op.f("ix_label_production_sources_run_id"), "label_production_sources", ["run_id"], unique=False)
    op.create_index(op.f("ix_label_production_sources_source_lot_id"), "label_production_sources", ["source_lot_id"], unique=False)

    op.create_table(
        "label_production_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["label_production_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_label_production_event_run_time", "label_production_events", ["run_id", "occurred_at"], unique=False)
    op.create_index(op.f("ix_label_production_events_organization_id"), "label_production_events", ["organization_id"], unique=False)
    op.create_index(op.f("ix_label_production_events_facility_id"), "label_production_events", ["facility_id"], unique=False)
    op.create_index(op.f("ix_label_production_events_run_id"), "label_production_events", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_label_production_events_run_id"), table_name="label_production_events")
    op.drop_index(op.f("ix_label_production_events_facility_id"), table_name="label_production_events")
    op.drop_index(op.f("ix_label_production_events_organization_id"), table_name="label_production_events")
    op.drop_index("ix_label_production_event_run_time", table_name="label_production_events")
    op.drop_table("label_production_events")

    op.drop_index(op.f("ix_label_production_sources_source_lot_id"), table_name="label_production_sources")
    op.drop_index(op.f("ix_label_production_sources_run_id"), table_name="label_production_sources")
    op.drop_index(op.f("ix_label_production_sources_facility_id"), table_name="label_production_sources")
    op.drop_index(op.f("ix_label_production_sources_organization_id"), table_name="label_production_sources")
    op.drop_table("label_production_sources")

    op.drop_index(op.f("ix_label_production_runs_product_id"), table_name="label_production_runs")
    op.drop_index(op.f("ix_label_production_runs_facility_id"), table_name="label_production_runs")
    op.drop_index(op.f("ix_label_production_runs_organization_id"), table_name="label_production_runs")
    op.drop_index("ix_label_production_facility_status", table_name="label_production_runs")
    op.drop_table("label_production_runs")
