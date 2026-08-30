"""Add first-class reconciliation facts to traceability transactions.

Revision ID: 0056_trace_reconciliation
Revises: 0055_receiving_preflight
"""

import sqlalchemy as sa
from alembic import op

revision = "0056_trace_reconciliation"
down_revision = "0055_receiving_preflight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("traceability_transactions")}
    columns = (
        sa.Column("jurisdiction", sa.String(16), nullable=False, server_default=""),
        sa.Column("environment", sa.String(24), nullable=False, server_default=""),
        sa.Column("direction", sa.String(16), nullable=False, server_default="outbound"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("local_state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("provider_state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("readback_result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("mismatch_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("reconciliation_evidence_json", sa.Text(), nullable=False, server_default="{}"),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("traceability_transactions", column)
    op.create_index(
        "ix_traceability_tx_reconciliation",
        "traceability_transactions",
        ["organization_id", "facility_id", "retry_eligible", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_traceability_tx_reconciliation", table_name="traceability_transactions")
    for name in (
        "reconciliation_evidence_json",
        "mismatch_reason",
        "readback_result_json",
        "provider_state_json",
        "local_state_json",
        "retry_eligible",
        "last_attempt_at",
        "direction",
        "environment",
        "jurisdiction",
    ):
        op.drop_column("traceability_transactions", name)
