"""Add the missing Package Studio production-order foreign-key index.

Revision ID: 0019_package_studio_production_order_index
Revises: 0018_traceability_transactions
"""

from alembic import op

revision = "0019_package_studio_production_order_index"
down_revision = "0018_traceability_transactions"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_package_studio_runs_production_order_id"


def upgrade() -> None:
    op.execute(
        f"create index if not exists {INDEX_NAME} "
        "on package_studio_runs(production_order_id)"
    )


def downgrade() -> None:
    op.execute(f"drop index if exists {INDEX_NAME}")
