"""Add hosted DoobieCommerce storefronts and approval queue.

Revision ID: 0048_commerce_storefronts
Revises: 0047_prod_schedule
"""

from alembic import op
import sqlalchemy as sa

revision = "0048_commerce_storefronts"
down_revision = "0047_prod_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_storefronts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("subdomain", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("headline", sa.String(255), nullable=False, server_default="Wholesale ordering"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("logo_url", sa.String(2048), nullable=False, server_default=""),
        sa.Column("hero_image_url", sa.String(2048), nullable=False, server_default=""),
        sa.Column("accent_color", sa.String(16), nullable=False, server_default="#8abf55"),
        sa.Column("contact_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("order_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_commerce_storefront_org_slug"),
        sa.UniqueConstraint("subdomain", name="uq_commerce_storefront_subdomain"),
    )
    op.create_index("ix_commerce_storefronts_organization_id", "commerce_storefronts", ["organization_id"])
    op.create_index("ix_commerce_storefronts_facility_id", "commerce_storefronts", ["facility_id"])
    op.create_index("ix_commerce_storefront_facility", "commerce_storefronts", ["facility_id", "published"])

    op.create_table(
        "commerce_storefront_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storefront_id", sa.String(36), sa.ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("minimum_quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("case_quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storefront_id", "product_id", name="uq_commerce_storefront_product"),
        sa.CheckConstraint("price_usd >= 0", name="ck_commerce_storefront_product_price"),
        sa.CheckConstraint("minimum_quantity > 0", name="ck_commerce_storefront_product_minimum"),
        sa.CheckConstraint("case_quantity > 0", name="ck_commerce_storefront_product_case"),
    )
    op.create_index("ix_commerce_storefront_products_organization_id", "commerce_storefront_products", ["organization_id"])
    op.create_index("ix_commerce_storefront_products_storefront_id", "commerce_storefront_products", ["storefront_id"])
    op.create_index("ix_commerce_storefront_products_product_id", "commerce_storefront_products", ["product_id"])
    op.create_index("ix_commerce_storefront_products_storefront", "commerce_storefront_products", ["storefront_id", "active", "sort_order"])

    op.create_table(
        "commerce_storefront_order_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storefront_id", sa.String(36), sa.ForeignKey("commerce_storefronts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_company", sa.String(255), nullable=False),
        sa.Column("buyer_license", sa.String(255), nullable=False, server_default=""),
        sa.Column("buyer_contact", sa.String(255), nullable=False),
        sa.Column("buyer_email", sa.String(320), nullable=False),
        sa.Column("buyer_phone", sa.String(64), nullable=False, server_default=""),
        sa.Column("purchase_order_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("requested_delivery_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("lines_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("estimated_subtotal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="submitted"),
        sa.Column("partner_id", sa.String(36), sa.ForeignKey("commercial_trade_partners.id", ondelete="SET NULL"), nullable=True),
        sa.Column("commercial_order_id", sa.String(36), sa.ForeignKey("commercial_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status in ('submitted','approved','rejected')", name="ck_commerce_storefront_request_status"),
    )
    op.create_index("ix_commerce_storefront_order_requests_organization_id", "commerce_storefront_order_requests", ["organization_id"])
    op.create_index("ix_commerce_storefront_order_requests_facility_id", "commerce_storefront_order_requests", ["facility_id"])
    op.create_index("ix_commerce_storefront_order_requests_storefront_id", "commerce_storefront_order_requests", ["storefront_id"])
    op.create_index("ix_commerce_storefront_order_requests_partner_id", "commerce_storefront_order_requests", ["partner_id"])
    op.create_index("ix_commerce_storefront_order_requests_commercial_order_id", "commerce_storefront_order_requests", ["commercial_order_id"])
    op.create_index("ix_commerce_storefront_request_facility_status", "commerce_storefront_order_requests", ["facility_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_table("commerce_storefront_order_requests")
    op.drop_table("commerce_storefront_products")
    op.drop_table("commerce_storefronts")
