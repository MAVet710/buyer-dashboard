"""Add provider-neutral traceability transaction and reconciliation ledger.

Revision ID: 0018_traceability_transactions
Revises: 0017_package_studio
"""

from alembic import op

from modules.traceability.models import TraceabilityTransaction, TraceabilityTransactionAttempt

revision = "0018_traceability_transactions"
down_revision = "0017_package_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    TraceabilityTransaction.__table__.create(bind=bind, checkfirst=True)
    TraceabilityTransactionAttempt.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table traceability_transactions enable row level security")
        op.execute("alter table traceability_transaction_attempts enable row level security")


def downgrade() -> None:
    op.drop_table("traceability_transaction_attempts")
    op.drop_table("traceability_transactions")
