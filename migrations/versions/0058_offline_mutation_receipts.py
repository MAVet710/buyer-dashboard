"""Add tenant-scoped idempotency receipts for approved offline mutations.

Revision ID: 0058_offline_mutation_receipts
Revises: 0057_cultivation_operations
"""

import sqlalchemy as sa
from alembic import op

revision = "0058_offline_mutation_receipts"
down_revision = "0057_cultivation_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offline_mutation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("endpoint_key", sa.String(96), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("parent_entity_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "endpoint_key",
            "idempotency_key",
            name="uq_offline_mutation_receipt_scope_key",
        ),
    )
    op.create_index("ix_offline_mutation_receipts_organization_id", "offline_mutation_receipts", ["organization_id"])
    op.create_index("ix_offline_mutation_receipts_facility_id", "offline_mutation_receipts", ["facility_id"])
    op.create_index(
        "ix_offline_mutation_receipts_scope_time",
        "offline_mutation_receipts",
        ["organization_id", "facility_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("offline_mutation_receipts")
