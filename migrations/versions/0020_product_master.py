"""Add canonical Product Master extension tables.

Revision ID: 0020_product_master
Revises: 0019_pkgstudio_po_index
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_product_master"
down_revision = "0019_pkgstudio_po_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_master_profiles",
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("subcategory", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("strain", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("product_format", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id"),
        sa.UniqueConstraint("organization_id", "product_id", name="uq_product_master_profile_org_product"),
    )
    op.create_index("ix_product_master_profiles_organization_id", "product_master_profiles", ["organization_id"])
    op.create_index("ix_product_master_profile_brand", "product_master_profiles", ["organization_id", "brand"])
    op.create_index("ix_product_master_profile_category", "product_master_profiles", ["organization_id", "category"])

    op.create_table(
        "product_vendor_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("partner_id", sa.String(length=36), nullable=False),
        sa.Column("vendor_sku", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minimum_order_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("case_pack", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("lead_time_days >= 0", name="ck_product_vendor_lead_time"),
        sa.CheckConstraint("minimum_order_quantity >= 0", name="ck_product_vendor_moq"),
        sa.CheckConstraint("case_pack >= 0", name="ck_product_vendor_case_pack"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["commercial_trade_partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "partner_id", name="uq_product_vendor_product_partner"),
    )
    op.create_index("ix_product_vendor_links_organization_id", "product_vendor_links", ["organization_id"])
    op.create_index("ix_product_vendor_links_product_id", "product_vendor_links", ["product_id"])
    op.create_index("ix_product_vendor_links_partner_id", "product_vendor_links", ["partner_id"])
    op.create_index("ix_product_vendor_org_active", "product_vendor_links", ["organization_id", "active"])
    op.create_index(
        "uq_product_vendor_active_primary",
        "product_vendor_links",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_primary and active"),
    )

    op.create_table(
        "product_external_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("system_name", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_name", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "system_name", "external_id", name="uq_product_external_org_system_id"),
        sa.UniqueConstraint("product_id", "system_name", "external_id", name="uq_product_external_product_system_id"),
    )
    op.create_index("ix_product_external_mappings_organization_id", "product_external_mappings", ["organization_id"])
    op.create_index("ix_product_external_mappings_product_id", "product_external_mappings", ["product_id"])
    op.create_index("ix_product_external_lookup", "product_external_mappings", ["organization_id", "system_name", "external_id"])

    op.create_table(
        "product_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=512), nullable=False),
        sa.Column("normalized_alias", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="manual"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "normalized_alias", name="uq_product_alias_org_normalized"),
    )
    op.create_index("ix_product_aliases_organization_id", "product_aliases", ["organization_id"])
    op.create_index("ix_product_aliases_product_id", "product_aliases", ["product_id"])
    op.create_index("ix_product_alias_product", "product_aliases", ["product_id", "active"])

    op.create_table(
        "product_value_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("partner_id", sa.String(length=36), nullable=True),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("previous_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="manual"),
        sa.Column("source_reference", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "value_type in ('unit_cost','landed_cost','retail_price','wholesale_price')",
            name="ck_product_value_type",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_product_value_amount"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["commercial_trade_partners.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_value_events_organization_id", "product_value_events", ["organization_id"])
    op.create_index("ix_product_value_events_product_id", "product_value_events", ["product_id"])
    op.create_index("ix_product_value_events_partner_id", "product_value_events", ["partner_id"])
    op.create_index("ix_product_value_product_time", "product_value_events", ["product_id", "effective_at"])
    op.create_index("ix_product_value_org_type_time", "product_value_events", ["organization_id", "value_type", "effective_at"])

    for table in (
        "product_master_profiles",
        "product_vendor_links",
        "product_external_mappings",
        "product_aliases",
        "product_value_events",
    ):
        op.execute(f"alter table public.{table} enable row level security")


def downgrade() -> None:
    op.drop_table("product_value_events")
    op.drop_table("product_aliases")
    op.drop_table("product_external_mappings")
    op.drop_table("product_vendor_links")
    op.drop_table("product_master_profiles")
