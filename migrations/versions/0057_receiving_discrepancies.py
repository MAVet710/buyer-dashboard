"""Add durable receiving discrepancy exceptions.

Revision ID: 0057_receiving_discrepancies
Revises: 0056_trace_reconciliation
"""

from alembic import op

from modules.traceability.models import ReceivingDiscrepancy

revision = "0057_receiving_discrepancies"
down_revision = "0056_trace_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ReceivingDiscrepancy.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table traceability_receiving_discrepancies enable row level security")


def downgrade() -> None:
    op.drop_table("traceability_receiving_discrepancies")
