"""Add cultivation room capacity, harvest plant assignment, and costing.

Revision ID: 0057_cultivation_operations
Revises: 0056_trace_reconciliation

The canonical cultivation_harvests table already exists in operational_moats.
This migration intentionally does not recreate or redefine that table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0057_cultivation_operations"
down_revision = "0056_trace_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cultivation_rooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("room_code", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("phase", sa.String(24), nullable=False, server_default=""),
        sa.Column("plant_capacity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("square_feet", sa.Float(), nullable=False, server_default="0"),
        sa.Column("target_cycle_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("facility_id", "room_code", name="uq_cultivation_room_facility_code"),
        sa.CheckConstraint("plant_capacity >= 0", name="ck_cultivation_room_capacity"),
        sa.CheckConstraint("square_feet >= 0", name="ck_cultivation_room_square_feet"),
        sa.CheckConstraint("target_cycle_days >= 0", name="ck_cultivation_room_cycle_days"),
    )
    op.create_index("ix_cultivation_rooms_organization_id", "cultivation_rooms", ["organization_id"])
    op.create_index("ix_cultivation_rooms_facility_id", "cultivation_rooms", ["facility_id"])
    op.create_index("ix_cultivation_rooms_facility_active", "cultivation_rooms", ["facility_id", "active"])

    op.create_table(
        "cultivation_harvest_plants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("harvest_id", sa.String(36), sa.ForeignKey("cultivation_harvests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(255), nullable=False),
        sa.UniqueConstraint("harvest_id", "plant_id", name="uq_cultivation_harvest_plant"),
    )
    op.create_index("ix_cultivation_harvest_plants_organization_id", "cultivation_harvest_plants", ["organization_id"])
    op.create_index("ix_cultivation_harvest_plants_facility_id", "cultivation_harvest_plants", ["facility_id"])
    op.create_index("ix_cultivation_harvest_plants_harvest_id", "cultivation_harvest_plants", ["harvest_id"])
    op.create_index("ix_cultivation_harvest_plants_plant", "cultivation_harvest_plants", ["plant_id"])

    op.create_table(
        "cultivation_cost_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("cost_type", sa.String(24), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("unit_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint("entity_type in ('plant','harvest','room')", name="ck_cultivation_cost_entity_type"),
        sa.CheckConstraint("cost_type in ('labor','material','overhead')", name="ck_cultivation_cost_type"),
        sa.CheckConstraint("quantity >= 0", name="ck_cultivation_cost_quantity"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_cultivation_cost_unit_cost"),
        sa.CheckConstraint("amount >= 0", name="ck_cultivation_cost_amount"),
    )
    op.create_index("ix_cultivation_cost_entries_organization_id", "cultivation_cost_entries", ["organization_id"])
    op.create_index("ix_cultivation_cost_entries_facility_id", "cultivation_cost_entries", ["facility_id"])
    op.create_index("ix_cultivation_cost_entries_entity", "cultivation_cost_entries", ["organization_id", "facility_id", "entity_type", "entity_id", "occurred_on"])


def downgrade() -> None:
    op.drop_table("cultivation_cost_entries")
    op.drop_table("cultivation_harvest_plants")
    op.drop_table("cultivation_rooms")
