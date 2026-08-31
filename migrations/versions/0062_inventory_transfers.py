"""Add durable cross-license inventory transfer genealogy.

Revision ID: 0062_inventory_transfers
Revises: 0061_cultivation_groups
"""

import sqlalchemy as sa
from alembic import op

revision = "0062_inventory_transfers"
down_revision = "0061_cultivation_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_transfers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_license_number", sa.String(160), nullable=False, server_default=""),
        sa.Column("destination_license_number", sa.String(160), nullable=False, server_default=""),
        sa.Column("source_facility_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("destination_facility_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("manifest_reference", sa.String(255), nullable=False),
        sa.Column("external_transfer_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="shipped"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "manifest_reference", name="uq_inventory_transfer_org_manifest"),
        sa.CheckConstraint("status in ('shipped','partially_received','received','cancelled')", name="ck_inventory_transfer_status"),
        sa.CheckConstraint("source_facility_id <> destination_facility_id", name="ck_inventory_transfer_distinct_facilities"),
    )
    op.create_index("ix_inventory_transfers_organization_id", "inventory_transfers", ["organization_id"])
    op.create_index("ix_inventory_transfers_source_facility_id", "inventory_transfers", ["source_facility_id"])
    op.create_index("ix_inventory_transfers_destination_facility_id", "inventory_transfers", ["destination_facility_id"])
    op.create_index("ix_inventory_transfer_source_status", "inventory_transfers", ["source_facility_id", "status", "shipped_at"])
    op.create_index("ix_inventory_transfer_destination_status", "inventory_transfers", ["destination_facility_id", "status", "shipped_at"])

    op.create_table(
        "inventory_transfer_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transfer_id", sa.String(36), sa.ForeignKey("inventory_transfers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("received_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("source_lot_code", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_package_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("destination_lot_code", sa.String(255), nullable=False, server_default=""),
        sa.Column("destination_package_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_transaction_id", sa.String(36), sa.ForeignKey("coman_inventory_transactions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_transaction_id", sa.String(36), sa.ForeignKey("coman_inventory_transactions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="shipped"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("transfer_id", "source_lot_id", name="uq_inventory_transfer_line_source_lot"),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_transfer_line_quantity"),
        sa.CheckConstraint("status in ('shipped','received','cancelled')", name="ck_inventory_transfer_line_status"),
    )
    op.create_index("ix_inventory_transfer_lines_organization_id", "inventory_transfer_lines", ["organization_id"])
    op.create_index("ix_inventory_transfer_lines_transfer_id", "inventory_transfer_lines", ["transfer_id"])
    op.create_index("ix_inventory_transfer_lines_product_id", "inventory_transfer_lines", ["product_id"])
    op.create_index("ix_inventory_transfer_lines_source_transaction_id", "inventory_transfer_lines", ["source_transaction_id"])
    op.create_index("ix_inventory_transfer_lines_destination_transaction_id", "inventory_transfer_lines", ["destination_transaction_id"])
    op.create_index("ix_inventory_transfer_line_source_lot", "inventory_transfer_lines", ["source_lot_id"])
    op.create_index("ix_inventory_transfer_line_destination_lot", "inventory_transfer_lines", ["destination_lot_id"])


def downgrade() -> None:
    op.drop_index("ix_inventory_transfer_line_destination_lot", table_name="inventory_transfer_lines")
    op.drop_index("ix_inventory_transfer_line_source_lot", table_name="inventory_transfer_lines")
    op.drop_index("ix_inventory_transfer_lines_destination_transaction_id", table_name="inventory_transfer_lines")
    op.drop_index("ix_inventory_transfer_lines_source_transaction_id", table_name="inventory_transfer_lines")
    op.drop_index("ix_inventory_transfer_lines_product_id", table_name="inventory_transfer_lines")
    op.drop_index("ix_inventory_transfer_lines_transfer_id", table_name="inventory_transfer_lines")
    op.drop_index("ix_inventory_transfer_lines_organization_id", table_name="inventory_transfer_lines")
    op.drop_table("inventory_transfer_lines")
    op.drop_index("ix_inventory_transfer_destination_status", table_name="inventory_transfers")
    op.drop_index("ix_inventory_transfer_source_status", table_name="inventory_transfers")
    op.drop_index("ix_inventory_transfers_destination_facility_id", table_name="inventory_transfers")
    op.drop_index("ix_inventory_transfers_source_facility_id", table_name="inventory_transfers")
    op.drop_index("ix_inventory_transfers_organization_id", table_name="inventory_transfers")
    op.drop_table("inventory_transfers")
