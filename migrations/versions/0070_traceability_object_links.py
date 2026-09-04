"""Add provider-neutral regulatory object identity links.

Revision ID: 0070_traceability_object_links
Revises: 0069_product_label_print_layouts
"""

import sqlalchemy as sa
from alembic import op

revision = "0070_traceability_object_links"
down_revision = "0069_product_label_print_layouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traceability_object_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("jurisdiction", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("environment", sa.String(length=24), nullable=False),
        sa.Column("license_number", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("provider_resource", sa.String(length=80), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=False),
        sa.Column("provider_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="verified"),
        sa.Column("source_transaction_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mismatch_reason", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider in ('metrc','biotrack','other')", name="ck_traceability_object_link_provider"),
        sa.CheckConstraint(
            "status in ('verified','stale','reconciliation_required')",
            name="ck_traceability_object_link_status",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_transaction_id"], ["traceability_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "entity_type",
            "entity_id",
            name="uq_traceability_object_link_local",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "provider_resource",
            "provider_id",
            name="uq_traceability_object_link_provider",
        ),
    )
    op.create_index("ix_traceability_object_links_organization_id", "traceability_object_links", ["organization_id"])
    op.create_index("ix_traceability_object_links_facility_id", "traceability_object_links", ["facility_id"])
    op.create_index("ix_traceability_object_links_source_transaction_id", "traceability_object_links", ["source_transaction_id"])
    op.create_index(
        "ix_traceability_object_link_local_lookup",
        "traceability_object_links",
        ["organization_id", "facility_id", "provider", "environment", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_traceability_object_link_provider_lookup",
        "traceability_object_links",
        ["organization_id", "facility_id", "provider", "environment", "provider_resource", "provider_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_traceability_object_link_provider_lookup", table_name="traceability_object_links")
    op.drop_index("ix_traceability_object_link_local_lookup", table_name="traceability_object_links")
    op.drop_index("ix_traceability_object_links_source_transaction_id", table_name="traceability_object_links")
    op.drop_index("ix_traceability_object_links_facility_id", table_name="traceability_object_links")
    op.drop_index("ix_traceability_object_links_organization_id", table_name="traceability_object_links")
    op.drop_table("traceability_object_links")
