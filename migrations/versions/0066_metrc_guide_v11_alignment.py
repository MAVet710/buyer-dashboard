"""Add audit-safe Metrc guide v11 correction state.

Revision ID: 0066_metrc_guide_v11_alignment
Revises: 0065_metrc_process_readiness
"""

import sqlalchemy as sa
from alembic import op

revision = "0066_metrc_guide_v11_alignment"
down_revision = "0065_metrc_process_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metrc_harvest_waste_projections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("waste_record_id", sa.String(length=36), nullable=False),
        sa.Column("material_loss_id", sa.String(length=36), nullable=False),
        sa.Column("discontinued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discontinued_by", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("provider_reference", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_loss_id"], ["material_transformation_losses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["waste_record_id"], ["cultivation_waste_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_loss_id", name="uq_metrc_harvest_waste_projection_loss"),
        sa.UniqueConstraint("waste_record_id", name="uq_metrc_harvest_waste_projection_waste"),
    )
    op.create_index(
        "ix_metrc_harvest_waste_projection_scope",
        "metrc_harvest_waste_projections",
        ["organization_id", "facility_id", "discontinued_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metrc_harvest_waste_projections_organization_id"),
        "metrc_harvest_waste_projections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metrc_harvest_waste_projections_facility_id"),
        "metrc_harvest_waste_projections",
        ["facility_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metrc_harvest_waste_projections_waste_record_id"),
        "metrc_harvest_waste_projections",
        ["waste_record_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metrc_harvest_waste_projections_material_loss_id"),
        "metrc_harvest_waste_projections",
        ["material_loss_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_metrc_harvest_waste_projections_material_loss_id"), table_name="metrc_harvest_waste_projections")
    op.drop_index(op.f("ix_metrc_harvest_waste_projections_waste_record_id"), table_name="metrc_harvest_waste_projections")
    op.drop_index(op.f("ix_metrc_harvest_waste_projections_facility_id"), table_name="metrc_harvest_waste_projections")
    op.drop_index(op.f("ix_metrc_harvest_waste_projections_organization_id"), table_name="metrc_harvest_waste_projections")
    op.drop_index("ix_metrc_harvest_waste_projection_scope", table_name="metrc_harvest_waste_projections")
    op.drop_table("metrc_harvest_waste_projections")
