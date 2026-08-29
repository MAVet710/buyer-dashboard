"""Add storefront quantity breaks, delivery windows, and PO attachments.

Revision ID: 0051_storefront_order_terms
Revises: 0050_regulatory_mappings
"""

from alembic import op
import sqlalchemy as sa


revision = "0051_storefront_order_terms"
down_revision = "0050_regulatory_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commerce_storefront_products", sa.Column("quantity_breaks_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("commerce_storefront_order_requests", sa.Column("requested_delivery_window", sa.String(80), nullable=False, server_default=""))
    op.create_table(
        "commerce_storefront_order_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("commerce_storefront_order_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False, server_default="purchase_order"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "kind", name="uq_commerce_storefront_order_attachment_kind"),
    )
    op.create_index("ix_commerce_storefront_order_attachment_org", "commerce_storefront_order_attachments", ["organization_id"])
    op.create_index("ix_commerce_storefront_order_attachment_facility", "commerce_storefront_order_attachments", ["facility_id"])
    op.create_index("ix_commerce_storefront_order_attachment_request_id", "commerce_storefront_order_attachments", ["request_id"])
    op.create_index("ix_commerce_storefront_order_attachment_request", "commerce_storefront_order_attachments", ["organization_id", "facility_id", "request_id"])


def downgrade() -> None:
    op.drop_index("ix_commerce_storefront_order_attachment_request", table_name="commerce_storefront_order_attachments")
    op.drop_index("ix_commerce_storefront_order_attachment_request_id", table_name="commerce_storefront_order_attachments")
    op.drop_index("ix_commerce_storefront_order_attachment_facility", table_name="commerce_storefront_order_attachments")
    op.drop_index("ix_commerce_storefront_order_attachment_org", table_name="commerce_storefront_order_attachments")
    op.drop_table("commerce_storefront_order_attachments")
    op.drop_column("commerce_storefront_order_requests", "requested_delivery_window")
    op.drop_column("commerce_storefront_products", "quantity_breaks_json")
