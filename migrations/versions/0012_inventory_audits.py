"""Add durable physical inventory audits and reconciliation lines.

Revision ID: 0012_inventory_audits
Revises: 0011_commercial_order_fulfillment
"""

from alembic import op
import sqlalchemy as sa

from modules.coman.models import InventoryAudit, InventoryAuditLine, InventoryAuditScan

revision = "0012_inventory_audits"
down_revision = "0011_commercial_order_fulfillment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    product_columns = {column["name"] for column in sa.inspect(bind).get_columns("coman_products")}
    for name, column in (
        ("retail_price", sa.Column("retail_price", sa.Float(), nullable=False, server_default="0")),
        ("upc", sa.Column("upc", sa.String(length=64), nullable=False, server_default="")),
        ("external_product_id", sa.Column("external_product_id", sa.String(length=120), nullable=False, server_default="")),
    ):
        if name not in product_columns:
            op.add_column("coman_products", column)
    lot_columns = {column["name"] for column in sa.inspect(bind).get_columns("coman_inventory_lots")}
    for name, column in (
        ("external_inventory_id", sa.Column("external_inventory_id", sa.String(length=120), nullable=False, server_default="")),
        ("barcode_value", sa.Column("barcode_value", sa.String(length=512), nullable=False, server_default="")),
    ):
        if name not in lot_columns:
            op.add_column("coman_inventory_lots", column)
    existing_product_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("coman_products")
    }
    for name, column in (
        ("ix_coman_products_upc", "upc"),
        ("ix_coman_products_external_product_id", "external_product_id"),
    ):
        if name not in existing_product_indexes:
            op.create_index(name, "coman_products", [column])
    existing_lot_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("coman_inventory_lots")
    }
    for name, column in (
        ("ix_coman_inventory_lots_external_inventory_id", "external_inventory_id"),
        ("ix_coman_inventory_lots_barcode_value", "barcode_value"),
    ):
        if name not in existing_lot_indexes:
            op.create_index(name, "coman_inventory_lots", [column])
    for model in (InventoryAudit, InventoryAuditLine, InventoryAuditScan):
        model.__table__.create(bind=bind, checkfirst=True)
        if bind.dialect.name == "postgresql":
            op.execute(f"alter table {model.__tablename__} enable row level security")


def downgrade() -> None:
    op.drop_table("inventory_audit_scans")
    op.drop_table("inventory_audit_lines")
    op.drop_table("inventory_audits")
    for name in ("barcode_value", "external_inventory_id"):
        op.drop_column("coman_inventory_lots", name)
    for name in ("external_product_id", "upc", "retail_price"):
        op.drop_column("coman_products", name)
