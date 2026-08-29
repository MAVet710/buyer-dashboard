"""Add draft/published Storefront Studio designs and tenant-scoped image assets.

Revision ID: 0052_storefront_studio
Revises: 0051_storefront_order_terms
"""

from alembic import op
import sqlalchemy as sa


revision = "0052_storefront_studio"
down_revision = "0051_storefront_order_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_storefront_studio",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storefront_id", sa.String(36), sa.ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("published_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storefront_id", name="uq_commerce_storefront_studio_storefront"),
    )
    op.create_index("ix_commerce_storefront_studio_organization_id", "commerce_storefront_studio", ["organization_id"])
    op.create_index("ix_commerce_storefront_studio_facility_id", "commerce_storefront_studio", ["facility_id"])
    op.create_index("ix_commerce_storefront_studio_storefront_id", "commerce_storefront_studio", ["storefront_id"])
    op.create_index("ix_commerce_storefront_studio_scope", "commerce_storefront_studio", ["organization_id", "facility_id"])

    op.create_table(
        "commerce_storefront_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storefront_id", sa.String(36), sa.ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commerce_storefront_assets_organization_id", "commerce_storefront_assets", ["organization_id"])
    op.create_index("ix_commerce_storefront_assets_facility_id", "commerce_storefront_assets", ["facility_id"])
    op.create_index("ix_commerce_storefront_assets_storefront_id", "commerce_storefront_assets", ["storefront_id"])
    op.create_index("ix_commerce_storefront_asset_scope", "commerce_storefront_assets", ["organization_id", "facility_id", "storefront_id"])
    op.create_index("ix_commerce_storefront_asset_kind", "commerce_storefront_assets", ["storefront_id", "kind", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_commerce_storefront_asset_kind", table_name="commerce_storefront_assets")
    op.drop_index("ix_commerce_storefront_asset_scope", table_name="commerce_storefront_assets")
    op.drop_index("ix_commerce_storefront_assets_storefront_id", table_name="commerce_storefront_assets")
    op.drop_index("ix_commerce_storefront_assets_facility_id", table_name="commerce_storefront_assets")
    op.drop_index("ix_commerce_storefront_assets_organization_id", table_name="commerce_storefront_assets")
    op.drop_table("commerce_storefront_assets")

    op.drop_index("ix_commerce_storefront_studio_scope", table_name="commerce_storefront_studio")
    op.drop_index("ix_commerce_storefront_studio_storefront_id", table_name="commerce_storefront_studio")
    op.drop_index("ix_commerce_storefront_studio_facility_id", table_name="commerce_storefront_studio")
    op.drop_index("ix_commerce_storefront_studio_organization_id", table_name="commerce_storefront_studio")
    op.drop_table("commerce_storefront_studio")
