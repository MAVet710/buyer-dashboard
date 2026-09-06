"""Add supplier portal grants and staged purchasing offers.

Revision ID: 0074_supplier_portal_offers
Revises: 0073_hydration_checkpoints
"""

import sqlalchemy as sa
from alembic import op

revision = "0074_supplier_portal_offers"
down_revision = "0073_hydration_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_portal_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("portal_access_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("partner_id", sa.String(length=36), nullable=False),
        sa.Column("permissions_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["commercial_trade_partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["portal_access_id"], ["partner_portal_access.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portal_access_id", name="uq_supplier_portal_grant_access"),
    )
    op.create_index("ix_supplier_portal_grants_portal_access_id", "supplier_portal_grants", ["portal_access_id"])
    op.create_index("ix_supplier_portal_grants_organization_id", "supplier_portal_grants", ["organization_id"])
    op.create_index("ix_supplier_portal_grants_facility_id", "supplier_portal_grants", ["facility_id"])
    op.create_index("ix_supplier_portal_grants_partner_id", "supplier_portal_grants", ["partner_id"])
    op.create_index("ix_supplier_portal_grant_partner", "supplier_portal_grants", ["organization_id", "partner_id"])

    op.create_table(
        "supplier_offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("offer_group_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("supersedes_offer_id", sa.String(length=36), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("partner_id", sa.String(length=36), nullable=False),
        sa.Column("portal_access_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("promotion_terms", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_by", sa.String(length=255), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('submitted','under_review','accepted','rejected','withdrawn','superseded','expired')",
            name="ck_supplier_offer_status",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["commercial_trade_partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["portal_access_id"], ["partner_portal_access.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_offer_id"], ["supplier_offers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_group_id", "revision", name="uq_supplier_offer_revision"),
    )
    for column in ("offer_group_id", "supersedes_offer_id", "organization_id", "facility_id", "partner_id", "portal_access_id"):
        op.create_index(f"ix_supplier_offers_{column}", "supplier_offers", [column])
    op.create_index("ix_supplier_offer_facility_status", "supplier_offers", ["facility_id", "status", "submitted_at"])
    op.create_index("ix_supplier_offer_partner_group", "supplier_offers", ["partner_id", "offer_group_id", "revision"])

    op.create_table(
        "supplier_offer_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("offer_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("supplier_sku", sa.String(length=160), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("strain", sa.String(length=255), nullable=False),
        sa.Column("form", sa.String(length=160), nullable=False),
        sa.Column("package_size", sa.Float(), nullable=True),
        sa.Column("package_size_unit", sa.String(length=40), nullable=False),
        sa.Column("available_quantity", sa.Float(), nullable=False),
        sa.Column("availability_unit", sa.String(length=40), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("price_basis", sa.String(length=40), nullable=False),
        sa.Column("minimum_order_quantity", sa.Float(), nullable=False),
        sa.Column("minimum_order_unit", sa.String(length=40), nullable=False),
        sa.Column("batch_lot_identifier", sa.String(length=255), nullable=False),
        sa.Column("coa_reference", sa.String(length=1024), nullable=False),
        sa.Column("sample_status", sa.String(length=24), nullable=False),
        sa.Column("promotion_terms", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("available_quantity >= 0", name="ck_supplier_offer_line_available"),
        sa.CheckConstraint("unit_price >= 0", name="ck_supplier_offer_line_price"),
        sa.CheckConstraint("minimum_order_quantity >= 0", name="ck_supplier_offer_line_minimum"),
        sa.CheckConstraint(
            "sample_status in ('none','offered','requested','approved','sent','received','declined')",
            name="ck_supplier_offer_line_sample_status",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["supplier_offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("offer_id", "organization_id", "facility_id", "product_id"):
        op.create_index(f"ix_supplier_offer_lines_{column}", "supplier_offer_lines", [column])
    op.create_index("ix_supplier_offer_line_offer", "supplier_offer_lines", ["offer_id", "position"])
    op.create_index("ix_supplier_offer_line_product", "supplier_offer_lines", ["organization_id", "product_id"])


def downgrade() -> None:
    op.drop_index("ix_supplier_offer_line_product", table_name="supplier_offer_lines")
    op.drop_index("ix_supplier_offer_line_offer", table_name="supplier_offer_lines")
    for column in ("product_id", "facility_id", "organization_id", "offer_id"):
        op.drop_index(f"ix_supplier_offer_lines_{column}", table_name="supplier_offer_lines")
    op.drop_table("supplier_offer_lines")

    op.drop_index("ix_supplier_offer_partner_group", table_name="supplier_offers")
    op.drop_index("ix_supplier_offer_facility_status", table_name="supplier_offers")
    for column in ("portal_access_id", "partner_id", "facility_id", "organization_id", "supersedes_offer_id", "offer_group_id"):
        op.drop_index(f"ix_supplier_offers_{column}", table_name="supplier_offers")
    op.drop_table("supplier_offers")

    op.drop_index("ix_supplier_portal_grant_partner", table_name="supplier_portal_grants")
    for column in ("partner_id", "facility_id", "organization_id", "portal_access_id"):
        op.drop_index(f"ix_supplier_portal_grants_{column}", table_name="supplier_portal_grants")
    op.drop_table("supplier_portal_grants")
