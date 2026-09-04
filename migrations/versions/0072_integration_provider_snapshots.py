"""Add current provider-owned integration snapshots.

Revision ID: 0072_integration_provider_snapshots
Revises: 0071_alpha_operating_modes
"""

import sqlalchemy as sa
from alembic import op

revision = "0072_integration_provider_snapshots"
down_revision = "0071_alpha_operating_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_provider_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=24), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("provider_label", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("raw_payload_json", sa.Text(), nullable=False),
        sa.Column("normalized_payload_json", sa.Text(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("snapshot_run_id", sa.String(length=36), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider in ('metrc','biotrack','quickbooks','metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')",
            name="ck_integration_provider_snapshot_provider",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "resource",
            "external_id",
            name="uq_integration_provider_snapshot_identity",
        ),
    )
    op.create_index(
        "ix_integration_provider_snapshot_current",
        "integration_provider_snapshots",
        ["organization_id", "facility_id", "provider", "resource", "present"],
    )
    op.create_index(
        "ix_integration_provider_snapshot_seen",
        "integration_provider_snapshots",
        ["facility_id", "provider", "last_seen_at"],
    )
    op.create_index(
        "ix_integration_provider_snapshots_organization_id",
        "integration_provider_snapshots",
        ["organization_id"],
    )
    op.create_index(
        "ix_integration_provider_snapshots_facility_id",
        "integration_provider_snapshots",
        ["facility_id"],
    )
    op.create_index(
        "ix_integration_provider_snapshots_snapshot_run_id",
        "integration_provider_snapshots",
        ["snapshot_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_provider_snapshots_snapshot_run_id", table_name="integration_provider_snapshots")
    op.drop_index("ix_integration_provider_snapshots_facility_id", table_name="integration_provider_snapshots")
    op.drop_index("ix_integration_provider_snapshots_organization_id", table_name="integration_provider_snapshots")
    op.drop_index("ix_integration_provider_snapshot_seen", table_name="integration_provider_snapshots")
    op.drop_index("ix_integration_provider_snapshot_current", table_name="integration_provider_snapshots")
    op.drop_table("integration_provider_snapshots")
