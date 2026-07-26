"""Add durable commercial orders, lot allocation, and fulfillment links.

Revision ID: 0011_commercial_order_fulfillment
Revises: 0010_catalog_nomenclature_mapper
"""

from alembic import op
import sqlalchemy as sa

from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    OrderLotAllocation,
    TradePartner,
)

revision = "0011_commercial_order_fulfillment"
down_revision = "0010_catalog_nomenclature_mapper"
branch_labels = None
depends_on = None


def _column_names(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    for model in (
        TradePartner,
        CommercialOrder,
        CommercialOrderLine,
        OrderLotAllocation,
    ):
        model.__table__.create(bind=bind, checkfirst=True)
        if bind.dialect.name == "postgresql":
            op.execute(f"alter table {model.__tablename__} enable row level security")

    transaction_columns = _column_names(bind, "coman_inventory_transactions")
    if "commercial_order_id" not in transaction_columns:
        op.add_column(
            "coman_inventory_transactions",
            sa.Column("commercial_order_id", sa.String(length=36), nullable=True),
        )
    if "commercial_order_line_id" not in transaction_columns:
        op.add_column(
            "coman_inventory_transactions",
            sa.Column("commercial_order_line_id", sa.String(length=36), nullable=True),
        )
    if bind.dialect.name == "postgresql":
        op.execute(
            "create index if not exists ix_coman_inventory_transactions_commercial_order_id "
            "on public.coman_inventory_transactions(commercial_order_id)"
        )
        op.execute(
            "create index if not exists ix_coman_inventory_transactions_commercial_order_line_id "
            "on public.coman_inventory_transactions(commercial_order_line_id)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    transaction_columns = _column_names(bind, "coman_inventory_transactions")
    if "commercial_order_line_id" in transaction_columns:
        op.drop_column("coman_inventory_transactions", "commercial_order_line_id")
    if "commercial_order_id" in transaction_columns:
        op.drop_column("coman_inventory_transactions", "commercial_order_id")
    for table_name in (
        "commercial_order_lot_allocations",
        "commercial_order_lines",
        "commercial_orders",
        "commercial_trade_partners",
    ):
        op.drop_table(table_name)
