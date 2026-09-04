"""Add durable provider hydration page checkpoints.

Revision ID: 0073_hydration_checkpoints
Revises: 0072_provider_snapshots
"""

import sqlalchemy as sa
from alembic import op

revision = "0073_hydration_checkpoints"
down_revision = "0072_provider_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_hydration_page_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=24), nullable=False),
        sa.Column("resource_key", sa.String(length=160), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("page_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("records_json", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "resource_key",
            "generation_id",
            "page_number",
            name="uq_integration_hydration_page",
        ),
    )
    op.create_index(
        "ix_integration_hydration_page_resume",
        "integration_hydration_page_checkpoints",
        ["organization_id", "facility_id", "provider", "environment", "resource_key", "completed_at"],
    )
    op.create_index(
        "ix_integration_hydration_page_checkpoints_organization_id",
        "integration_hydration_page_checkpoints",
        ["organization_id"],
    )
    op.create_index(
        "ix_integration_hydration_page_checkpoints_facility_id",
        "integration_hydration_page_checkpoints",
        ["facility_id"],
    )
    op.create_index(
        "ix_integration_hydration_page_checkpoints_generation_id",
        "integration_hydration_page_checkpoints",
        ["generation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_hydration_page_checkpoints_generation_id", table_name="integration_hydration_page_checkpoints")
    op.drop_index("ix_integration_hydration_page_checkpoints_facility_id", table_name="integration_hydration_page_checkpoints")
    op.drop_index("ix_integration_hydration_page_checkpoints_organization_id", table_name="integration_hydration_page_checkpoints")
    op.drop_index("ix_integration_hydration_page_resume", table_name="integration_hydration_page_checkpoints")
    op.drop_table("integration_hydration_page_checkpoints")
