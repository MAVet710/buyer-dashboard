"""Add explicit alpha operating mode per facility.

Revision ID: 0071_alpha_operating_modes
Revises: 0070_traceability_object_links
"""

import sqlalchemy as sa
from alembic import op

revision = "0071_alpha_operating_modes"
down_revision = "0070_traceability_object_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alpha_operating_modes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode in ('doobielogic_sandbox','metrc_sandbox')",
            name="ck_alpha_operating_mode_mode",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "facility_id", name="uq_alpha_operating_mode_facility"),
    )
    op.create_index("ix_alpha_operating_modes_organization_id", "alpha_operating_modes", ["organization_id"])
    op.create_index("ix_alpha_operating_modes_facility_id", "alpha_operating_modes", ["facility_id"])
    op.create_index("ix_alpha_operating_mode_scope", "alpha_operating_modes", ["organization_id", "facility_id"])


def downgrade() -> None:
    op.drop_index("ix_alpha_operating_mode_scope", table_name="alpha_operating_modes")
    op.drop_index("ix_alpha_operating_modes_facility_id", table_name="alpha_operating_modes")
    op.drop_index("ix_alpha_operating_modes_organization_id", table_name="alpha_operating_modes")
    op.drop_table("alpha_operating_modes")
