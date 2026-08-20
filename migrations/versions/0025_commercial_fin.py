"""Add wholesale fulfillment, invoicing and A/R.

Revision ID: 0025_commercial_fin
Revises: 0024_production_erp
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_commercial_fin"
down_revision = "0024_production_erp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commercial_shipments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("commercial_order_id", sa.String(36), nullable=False),
        sa.Column("shipment_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("manifest_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("carrier", sa.String(255), nullable=False, server_default=""),
        sa.Column("tracking_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id","shipment_number", name="uq_commercial_shipment_org_number"),
        sa.CheckConstraint("status in ('planned','picking','packed','manifested','shipped','delivered','cancelled')", name="ck_commercial_shipment_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["commercial_order_id"], ["commercial_orders.id"], ondelete="CASCADE"),
    )
    for col in ("organization_id","facility_id","commercial_order_id"):
        op.create_index(f"ix_commercial_shipments_{col}", "commercial_shipments", [col])
    op.create_index("ix_commercial_shipment_facility_status", "commercial_shipments", ["facility_id","status","created_at"])

    op.create_table(
        "commercial_invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("commercial_order_id", sa.String(36), nullable=False),
        sa.Column("partner_id", sa.String(36), nullable=False),
        sa.Column("invoice_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("subtotal_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("discount_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tax_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("balance_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id","invoice_number", name="uq_commercial_invoice_org_number"),
        sa.CheckConstraint("status in ('draft','sent','partial','paid','overdue','void')", name="ck_commercial_invoice_status"),
        sa.CheckConstraint("subtotal_usd >= 0 and discount_usd >= 0 and tax_usd >= 0 and total_usd >= 0 and balance_usd >= 0", name="ck_commercial_invoice_amounts"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["commercial_order_id"], ["commercial_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["partner_id"], ["commercial_trade_partners.id"], ondelete="RESTRICT"),
    )
    for col in ("organization_id","facility_id","commercial_order_id","partner_id"):
        op.create_index(f"ix_commercial_invoices_{col}", "commercial_invoices", [col])
    op.create_index("ix_commercial_invoice_facility_status_due", "commercial_invoices", ["facility_id","status","due_date"])

    op.create_table(
        "commercial_invoice_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("invoice_id", sa.String(36), nullable=False),
        sa.Column("commercial_order_line_id", sa.String(36), nullable=True),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("unit_price_usd", sa.Float(), nullable=False),
        sa.Column("line_total_usd", sa.Float(), nullable=False),
        sa.UniqueConstraint("invoice_id","position", name="uq_commercial_invoice_line_position"),
        sa.CheckConstraint("quantity > 0 and unit_price_usd >= 0 and line_total_usd >= 0", name="ck_commercial_invoice_line_amounts"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["commercial_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["commercial_order_line_id"], ["commercial_order_lines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="RESTRICT"),
    )
    for col in ("organization_id","invoice_id","commercial_order_line_id","product_id"):
        op.create_index(f"ix_commercial_invoice_lines_{col}", "commercial_invoice_lines", [col])

    op.create_table(
        "commercial_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("invoice_id", sa.String(36), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(64), nullable=False, server_default="other"),
        sa.Column("reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("amount_usd > 0", name="ck_commercial_payment_amount"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["commercial_invoices.id"], ondelete="CASCADE"),
    )
    for col in ("organization_id","facility_id","invoice_id"):
        op.create_index(f"ix_commercial_payments_{col}", "commercial_payments", [col])
    op.create_index("ix_commercial_payment_invoice_date", "commercial_payments", ["invoice_id","payment_date"])

    op.create_table(
        "customer_price_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("partner_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("price_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("discount_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("partner_id","product_id", name="uq_customer_price_partner_product"),
        sa.CheckConstraint("price_usd >= 0 and discount_pct >= 0 and discount_pct <= 100", name="ck_customer_price_values"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["commercial_trade_partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="CASCADE"),
    )
    for col in ("organization_id","partner_id","product_id"):
        op.create_index(f"ix_customer_price_rules_{col}", "customer_price_rules", [col])
    op.create_index("ix_customer_price_org_active", "customer_price_rules", ["organization_id","active"])

    for table in ("commercial_shipments","commercial_invoices","commercial_invoice_lines","commercial_payments","customer_price_rules"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("customer_price_rules")
    op.drop_table("commercial_payments")
    op.drop_table("commercial_invoice_lines")
    op.drop_table("commercial_invoices")
    op.drop_table("commercial_shipments")
