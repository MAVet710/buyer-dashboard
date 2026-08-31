"""Add cultivation plant groups and first-class parent genealogy.

Revision ID: 0061_cultivation_groups
Revises: 0060_vertical_saleability
"""

import sqlalchemy as sa
from alembic import op

revision = "0061_cultivation_groups"
down_revision = "0060_vertical_saleability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cultivation_plant_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("group_code", sa.String(120), nullable=False),
        sa.Column("group_type", sa.String(32), nullable=False),
        sa.Column("strain_name", sa.String(255), nullable=False),
        sa.Column("room_code", sa.String(120), nullable=False, server_default="UNASSIGNED"),
        sa.Column("source_lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mother_plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("facility_id", "group_code", name="uq_cultivation_group_facility_code"),
        sa.CheckConstraint("group_type in ('clone_batch','seed_batch','nursery','vegetative','flowering')", name="ck_cultivation_group_type"),
        sa.CheckConstraint("status in ('active','closed','cancelled')", name="ck_cultivation_group_status"),
    )
    op.create_index("ix_cultivation_plant_groups_organization_id", "cultivation_plant_groups", ["organization_id"])
    op.create_index("ix_cultivation_plant_groups_facility_id", "cultivation_plant_groups", ["facility_id"])
    op.create_index("ix_cultivation_plant_groups_source_lot_id", "cultivation_plant_groups", ["source_lot_id"])
    op.create_index("ix_cultivation_plant_groups_mother_plant_id", "cultivation_plant_groups", ["mother_plant_id"])
    op.create_index("ix_cultivation_groups_facility_status", "cultivation_plant_groups", ["facility_id", "status", "group_type"])

    op.create_table(
        "cultivation_plant_group_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("cultivation_plant_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("added_by", sa.String(255), nullable=False),
        sa.UniqueConstraint("group_id", "plant_id", name="uq_cultivation_group_member"),
    )
    op.create_index("ix_cultivation_plant_group_members_organization_id", "cultivation_plant_group_members", ["organization_id"])
    op.create_index("ix_cultivation_plant_group_members_facility_id", "cultivation_plant_group_members", ["facility_id"])
    op.create_index("ix_cultivation_plant_group_members_group_id", "cultivation_plant_group_members", ["group_id"])
    op.create_index("ix_cultivation_group_members_plant", "cultivation_plant_group_members", ["plant_id"])

    op.create_table(
        "cultivation_plant_parent_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("child_plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("relationship", sa.String(24), nullable=False, server_default="mother"),
        sa.Column("linked_by", sa.String(255), nullable=False),
        sa.UniqueConstraint("child_plant_id", "relationship", name="uq_cultivation_plant_parent_relationship"),
        sa.CheckConstraint("relationship in ('mother','source_plant')", name="ck_cultivation_parent_relationship"),
    )
    op.create_index("ix_cultivation_plant_parent_links_organization_id", "cultivation_plant_parent_links", ["organization_id"])
    op.create_index("ix_cultivation_plant_parent_links_facility_id", "cultivation_plant_parent_links", ["facility_id"])
    op.create_index("ix_cultivation_plant_parent_links_child_plant_id", "cultivation_plant_parent_links", ["child_plant_id"])
    op.create_index("ix_cultivation_parent_links_parent", "cultivation_plant_parent_links", ["parent_plant_id"])


def downgrade() -> None:
    op.drop_index("ix_cultivation_parent_links_parent", table_name="cultivation_plant_parent_links")
    op.drop_index("ix_cultivation_plant_parent_links_child_plant_id", table_name="cultivation_plant_parent_links")
    op.drop_index("ix_cultivation_plant_parent_links_facility_id", table_name="cultivation_plant_parent_links")
    op.drop_index("ix_cultivation_plant_parent_links_organization_id", table_name="cultivation_plant_parent_links")
    op.drop_table("cultivation_plant_parent_links")
    op.drop_index("ix_cultivation_group_members_plant", table_name="cultivation_plant_group_members")
    op.drop_index("ix_cultivation_plant_group_members_group_id", table_name="cultivation_plant_group_members")
    op.drop_index("ix_cultivation_plant_group_members_facility_id", table_name="cultivation_plant_group_members")
    op.drop_index("ix_cultivation_plant_group_members_organization_id", table_name="cultivation_plant_group_members")
    op.drop_table("cultivation_plant_group_members")
    op.drop_index("ix_cultivation_groups_facility_status", table_name="cultivation_plant_groups")
    op.drop_index("ix_cultivation_plant_groups_mother_plant_id", table_name="cultivation_plant_groups")
    op.drop_index("ix_cultivation_plant_groups_source_lot_id", table_name="cultivation_plant_groups")
    op.drop_index("ix_cultivation_plant_groups_facility_id", table_name="cultivation_plant_groups")
    op.drop_index("ix_cultivation_plant_groups_organization_id", table_name="cultivation_plant_groups")
    op.drop_table("cultivation_plant_groups")
