"""Persist legacy Extraction Command Center run and toll fields.

Revision ID: 0038_extraction_parity_fields
Revises: 0037_function_acl_hardening
"""

from alembic import op
import sqlalchemy as sa

revision = "0038_extraction_parity_fields"
down_revision = "0037_function_acl_hardening"
branch_labels = None
depends_on = None

RUN_COLUMNS = (
    ("run_date", sa.Column("run_date", sa.Date(), nullable=True)),
    ("jurisdiction", sa.Column("jurisdiction", sa.String(64), nullable=False, server_default="")),
    ("facility_license_name", sa.Column("facility_license_name", sa.String(255), nullable=False, server_default="")),
    ("client_name_snapshot", sa.Column("client_name_snapshot", sa.String(255), nullable=False, server_default="")),
    ("manual_batch_id_internal", sa.Column("manual_batch_id_internal", sa.String(120), nullable=True)),
    ("input_material_type", sa.Column("input_material_type", sa.String(120), nullable=False, server_default="")),
    ("manual_input_weight_g", sa.Column("manual_input_weight_g", sa.Float(), nullable=False, server_default="0")),
    ("intermediate_output_g", sa.Column("intermediate_output_g", sa.Float(), nullable=False, server_default="0")),
    ("manual_finished_output_g", sa.Column("manual_finished_output_g", sa.Float(), nullable=False, server_default="0")),
    ("residual_loss_g", sa.Column("residual_loss_g", sa.Float(), nullable=False, server_default="0")),
    ("machine_line", sa.Column("machine_line", sa.String(160), nullable=False, server_default="")),
    ("metrc_package_id_input", sa.Column("metrc_package_id_input", sa.String(255), nullable=False, server_default="")),
    ("metrc_package_id_output", sa.Column("metrc_package_id_output", sa.String(255), nullable=False, server_default="")),
    ("metrc_manifest_or_transfer_id", sa.Column("metrc_manifest_or_transfer_id", sa.String(255), nullable=False, server_default="")),
    ("manual_coa_status", sa.Column("manual_coa_status", sa.String(32), nullable=False, server_default="pending")),
    ("manual_qa_hold", sa.Column("manual_qa_hold", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("processing_fee_usd", sa.Column("processing_fee_usd", sa.Float(), nullable=False, server_default="0")),
    ("estimated_revenue_usd", sa.Column("estimated_revenue_usd", sa.Float(), nullable=False, server_default="0")),
    ("manual_cogs_usd", sa.Column("manual_cogs_usd", sa.Float(), nullable=False, server_default="0")),
)

TOLL_COLUMNS = (
    ("jurisdiction", sa.Column("jurisdiction", sa.String(64), nullable=False, server_default="")),
    ("client_license_snapshot", sa.Column("client_license_snapshot", sa.String(255), nullable=False, server_default="")),
    ("material_received_at", sa.Column("material_received_at", sa.DateTime(timezone=True), nullable=True)),
    ("input_weight_g", sa.Column("input_weight_g", sa.Float(), nullable=False, server_default="0")),
    ("expected_output_g", sa.Column("expected_output_g", sa.Float(), nullable=False, server_default="0")),
    ("actual_output_g", sa.Column("actual_output_g", sa.Float(), nullable=False, server_default="0")),
    ("coa_status", sa.Column("coa_status", sa.String(32), nullable=False, server_default="pending")),
    ("job_status", sa.Column("job_status", sa.String(32), nullable=False, server_default="queued")),
)


def _add_missing(table: str, columns) -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    for name, column in columns:
        if name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_missing("extraction_runs", RUN_COLUMNS)
    _add_missing("extraction_toll_jobs", TOLL_COLUMNS)


def downgrade() -> None:
    for table, columns in (("extraction_toll_jobs", TOLL_COLUMNS), ("extraction_runs", RUN_COLUMNS)):
        existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        for name, _ in reversed(columns):
            if name in existing:
                op.drop_column(table, name)
