"""Add per-listing storefront sales units.

Revision ID: 0054_storefront_sales_units
Revises: 0053_user_permission_overrides
"""

from alembic import op
import sqlalchemy as sa


revision = "0054_storefront_sales_units"
down_revision = "0053_user_permission_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_storefront_product_sales_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storefront_id", sa.String(36), sa.ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sales_unit", sa.String(24), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storefront_id", "product_id", name="uq_storefront_product_sales_unit"),
    )
    op.create_index("ix_commerce_storefront_product_sales_units_organization_id", "commerce_storefront_product_sales_units", ["organization_id"])
    op.create_index("ix_commerce_storefront_product_sales_units_storefront_id", "commerce_storefront_product_sales_units", ["storefront_id"])
    op.create_index("ix_commerce_storefront_product_sales_units_product_id", "commerce_storefront_product_sales_units", ["product_id"])
    op.create_index("ix_storefront_product_sales_unit_scope", "commerce_storefront_product_sales_units", ["organization_id", "storefront_id"])


def downgrade() -> None:
    op.drop_index("ix_storefront_product_sales_unit_scope", table_name="commerce_storefront_product_sales_units")
    op.drop_index("ix_commerce_storefront_product_sales_units_product_id", table_name="commerce_storefront_product_sales_units")
    op.drop_index("ix_commerce_storefront_product_sales_units_storefront_id", table_name="commerce_storefront_product_sales_units")
    op.drop_index("ix_commerce_storefront_product_sales_units_organization_id", table_name="commerce_storefront_product_sales_units")
    op.drop_table("commerce_storefront_product_sales_units")
