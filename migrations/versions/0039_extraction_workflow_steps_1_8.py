"""Persist extraction workflow, formulation, METRC and stage-output fields.

Revision ID: 0039_extraction_step8
Revises: 0038_extraction_parity_fields
"""

from alembic import op
import sqlalchemy as sa

revision = "0039_extraction_step8"
down_revision = "0038_extraction_parity_fields"
branch_labels = None
depends_on = None

RUN_COLUMNS = (
    ("intermediate_product_type", sa.Column("intermediate_product_type", sa.String(160), nullable=False, server_default="")),
    ("final_product_type", sa.Column("final_product_type", sa.String(160), nullable=False, server_default="")),
    ("formulation_used", sa.Column("formulation_used", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("formulation_base_g", sa.Column("formulation_base_g", sa.Float(), nullable=False, server_default="0")),
    ("terpene_handling_mode", sa.Column("terpene_handling_mode", sa.String(160), nullable=False, server_default="Native / No Add-Back")),
    ("terpene_type", sa.Column("terpene_type", sa.String(160), nullable=False, server_default="")),
    ("terpene_source", sa.Column("terpene_source", sa.String(255), nullable=False, server_default="")),
    ("terpene_percentage", sa.Column("terpene_percentage", sa.Float(), nullable=False, server_default="0")),
    ("terpene_weight_g", sa.Column("terpene_weight_g", sa.Float(), nullable=False, server_default="0")),
    ("final_output_g", sa.Column("final_output_g", sa.Float(), nullable=False, server_default="0")),
    ("metrc_input_package_id", sa.Column("metrc_input_package_id", sa.String(255), nullable=False, server_default="")),
    ("metrc_intermediate_package_id", sa.Column("metrc_intermediate_package_id", sa.String(255), nullable=False, server_default="")),
    ("metrc_distillate_package_id", sa.Column("metrc_distillate_package_id", sa.String(255), nullable=False, server_default="")),
    ("metrc_formulation_package_id", sa.Column("metrc_formulation_package_id", sa.String(255), nullable=False, server_default="")),
    ("metrc_final_package_id", sa.Column("metrc_final_package_id", sa.String(255), nullable=False, server_default="")),
    ("extraction_output_g", sa.Column("extraction_output_g", sa.Float(), nullable=False, server_default="0")),
    ("purge_output_g", sa.Column("purge_output_g", sa.Float(), nullable=False, server_default="0")),
    ("crystallization_output_g", sa.Column("crystallization_output_g", sa.Float(), nullable=False, server_default="0")),
    ("sauce_fraction_g", sa.Column("sauce_fraction_g", sa.Float(), nullable=False, server_default="0")),
    ("diamond_fraction_g", sa.Column("diamond_fraction_g", sa.Float(), nullable=False, server_default="0")),
    ("crude_output_g", sa.Column("crude_output_g", sa.Float(), nullable=False, server_default="0")),
    ("winterized_output_g", sa.Column("winterized_output_g", sa.Float(), nullable=False, server_default="0")),
    ("filtered_output_g", sa.Column("filtered_output_g", sa.Float(), nullable=False, server_default="0")),
    ("decarbed_output_g", sa.Column("decarbed_output_g", sa.Float(), nullable=False, server_default="0")),
    ("distillate_output_g", sa.Column("distillate_output_g", sa.Float(), nullable=False, server_default="0")),
    ("wash_output_g", sa.Column("wash_output_g", sa.Float(), nullable=False, server_default="0")),
    ("dried_hash_output_g", sa.Column("dried_hash_output_g", sa.Float(), nullable=False, server_default="0")),
    ("sift_output_g", sa.Column("sift_output_g", sa.Float(), nullable=False, server_default="0")),
    ("rosin_output_g", sa.Column("rosin_output_g", sa.Float(), nullable=False, server_default="0")),
)

STAGE_COLUMNS = (
    ("stage_output_field", sa.Column("stage_output_field", sa.String(120), nullable=False, server_default="")),
    ("metrc_stage_input_id", sa.Column("metrc_stage_input_id", sa.String(255), nullable=False, server_default="")),
    ("metrc_stage_output_id", sa.Column("metrc_stage_output_id", sa.String(255), nullable=False, server_default="")),
)


def _add_missing(table: str, columns) -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    for name, column in columns:
        if name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_missing("extraction_runs", RUN_COLUMNS)
    _add_missing("extraction_stage_events", STAGE_COLUMNS)


def downgrade() -> None:
    for table, columns in (("extraction_stage_events", STAGE_COLUMNS), ("extraction_runs", RUN_COLUMNS)):
        existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        for name, _ in reversed(columns):
            if name in existing:
                op.drop_column(table, name)
