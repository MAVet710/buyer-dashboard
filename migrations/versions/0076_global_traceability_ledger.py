"""Add global reconciliation and exception metadata to traceability ledger.

Revision ID: 0076_global_traceability_ledger
Revises: 0075_product_ingredients
"""

from alembic import op
import sqlalchemy as sa

revision = "0076_global_traceability_ledger"
down_revision = "0075_product_ingredients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("traceability_transactions")}
    columns = (
        sa.Column("correlation_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("source", sa.String(64), nullable=False, server_default="application"),
        sa.Column("external_tag", sa.String(255), nullable=False, server_default=""),
        sa.Column("error_classification", sa.String(64), nullable=False, server_default=""),
        sa.Column("reconciliation_state", sa.String(64), nullable=False, server_default="pending"),
        sa.Column("resolution_state", sa.String(32), nullable=False, server_default="open"),
        sa.Column("parent_entity_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("parent_entity_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("related_entities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("resolved_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=False, server_default=""),
    )
    for column in columns:
        if column.name not in existing_columns:
            op.add_column("traceability_transactions", column)
    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("traceability_transactions")}
    indexes = (
        ("ix_traceability_tx_correlation", ["organization_id", "facility_id", "correlation_id"]),
        ("ix_traceability_tx_exception", ["organization_id", "facility_id", "environment", "resolution_state", "requested_at"]),
        ("ix_traceability_tx_external", ["organization_id", "facility_id", "provider", "environment", "external_reference"]),
    )
    for name, fields in indexes:
        if name not in existing_indexes:
            op.create_index(name, "traceability_transactions", fields)


def downgrade() -> None:
    bind = op.get_bind()
    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("traceability_transactions")}
    for name in ("ix_traceability_tx_external", "ix_traceability_tx_exception", "ix_traceability_tx_correlation"):
        if name in existing_indexes:
            op.drop_index(name, table_name="traceability_transactions")
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("traceability_transactions")}
    for name in (
        "resolution_note", "resolved_at", "resolved_by", "related_entities_json",
        "parent_entity_id", "parent_entity_type", "resolution_state",
        "reconciliation_state", "error_classification", "external_tag", "source", "correlation_id",
    ):
        if name in existing_columns:
            op.drop_column("traceability_transactions", name)
