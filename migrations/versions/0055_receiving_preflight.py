"""Add durable provider-confirmed receiving preflight evidence.

Revision ID: 0055_receiving_preflight
Revises: 0054_storefront_sales_units
"""

from alembic import op

from modules.traceability.models import ReceivingPreflight

revision = "0055_receiving_preflight"
down_revision = "0054_storefront_sales_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ReceivingPreflight.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table traceability_receiving_preflights enable row level security")


def downgrade() -> None:
    op.drop_table("traceability_receiving_preflights")
