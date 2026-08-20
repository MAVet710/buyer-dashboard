"""Add extraction resource usage intelligence.

Revision ID: 0022_extraction_intel
Revises: 0021_extraction_erp
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_extraction_intel"
down_revision = "0021_extraction_erp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_resource_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("stage_key", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("resource_type", sa.String(length=24), nullable=False),
        sa.Column("resource_name", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("recovered_quantity", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_reference", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "resource_type in ('solvent','utility','gas','consumable','water','other')",
            name="ck_extraction_resource_type",
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_extraction_resource_quantity"),
        sa.CheckConstraint(
            "recovered_quantity is null or recovered_quantity >= 0",
            name="ck_extraction_resource_recovered_nonnegative",
        ),
        sa.CheckConstraint(
            "recovered_quantity is null or recovered_quantity <= quantity",
            name="ck_extraction_resource_recovered_le_quantity",
        ),
        sa.CheckConstraint("cost_usd >= 0", name="ck_extraction_resource_cost"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_extraction_resource_events_organization_id", "extraction_resource_events", ["organization_id"])
    op.create_index("ix_extraction_resource_events_facility_id", "extraction_resource_events", ["facility_id"])
    op.create_index("ix_extraction_resource_events_run_id", "extraction_resource_events", ["run_id"])
    op.create_index("ix_extraction_resource_run_time", "extraction_resource_events", ["run_id", "occurred_at"])
    op.create_index(
        "ix_extraction_resource_facility_type",
        "extraction_resource_events",
        ["facility_id", "resource_type", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("extraction_resource_events")
