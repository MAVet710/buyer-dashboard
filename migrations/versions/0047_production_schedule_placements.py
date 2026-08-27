"""Add versioned production schedule placements.

Revision ID: 0047_prod_schedule
Revises: 0046_production_bom_standards
"""

from alembic import op
import sqlalchemy as sa

revision = "0047_prod_schedule"
down_revision = "0046_production_bom_standards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_schedule_placements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("production_order_id", sa.String(36), sa.ForeignKey("coman_production_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("machine_id", sa.String(36), sa.ForeignKey("coman_facility_machines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("planned_people", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("production_order_id", "version", name="uq_production_schedule_order_version"),
        sa.CheckConstraint("version > 0", name="ck_production_schedule_version_positive"),
        sa.CheckConstraint("planned_people >= 0", name="ck_production_schedule_people_nonnegative"),
        sa.CheckConstraint("scheduled_end_at > scheduled_start_at", name="ck_production_schedule_time_order"),
    )
    op.create_index("ix_production_schedule_placements_organization_id", "production_schedule_placements", ["organization_id"])
    op.create_index("ix_production_schedule_placements_facility_id", "production_schedule_placements", ["facility_id"])
    op.create_index("ix_production_schedule_placements_production_order_id", "production_schedule_placements", ["production_order_id"])
    op.create_index("ix_production_schedule_placements_machine_id", "production_schedule_placements", ["machine_id"])
    op.create_index("ix_production_schedule_facility_active_start", "production_schedule_placements", ["facility_id", "active", "scheduled_start_at"])
    op.create_index("ix_production_schedule_machine_active_time", "production_schedule_placements", ["machine_id", "active", "scheduled_start_at", "scheduled_end_at"])


def downgrade() -> None:
    op.drop_index("ix_production_schedule_machine_active_time", table_name="production_schedule_placements")
    op.drop_index("ix_production_schedule_facility_active_start", table_name="production_schedule_placements")
    op.drop_index("ix_production_schedule_placements_machine_id", table_name="production_schedule_placements")
    op.drop_index("ix_production_schedule_placements_production_order_id", table_name="production_schedule_placements")
    op.drop_index("ix_production_schedule_placements_facility_id", table_name="production_schedule_placements")
    op.drop_index("ix_production_schedule_placements_organization_id", table_name="production_schedule_placements")
    op.drop_table("production_schedule_placements")
