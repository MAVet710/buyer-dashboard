"""Add normalized durable retail sales.

Revision ID: 0030_retail_sales_ledger
Revises: 0029_dev_sandbox_ledger_reset
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_retail_sales_ledger"
down_revision = "0029_dev_sandbox_ledger_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retail_sales",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_record_id", sa.String(255), nullable=False),
        sa.Column("import_batch_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("sku", sa.String(120), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("net_sales", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "facility_id", "source_system", "source_record_id", name="uq_retail_sale_source_record"),
    )
    op.create_index("ix_retail_sales_facility_time", "retail_sales", ["facility_id", "sold_at"])
    op.create_index("ix_retail_sales_product_time", "retail_sales", ["product_id", "sold_at"])
    op.create_index("ix_retail_sales_organization_id", "retail_sales", ["organization_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("alter table public.retail_sales enable row level security")


def downgrade() -> None:
    op.drop_table("retail_sales")
