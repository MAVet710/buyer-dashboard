"""Add product-aware Label Studio print layout settings.

Revision ID: 0069_product_label_print_layouts
Revises: 0068_label_production_workflow
"""

import sqlalchemy as sa
from alembic import op

revision = "0069_product_label_print_layouts"
down_revision = "0068_label_production_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_packaging_profiles",
        sa.Column("label_layout", sa.String(length=32), nullable=False, server_default="compact_single"),
    )
    op.add_column(
        "product_packaging_profiles",
        sa.Column("label_width_in", sa.Float(), nullable=False, server_default="3.5"),
    )
    op.add_column(
        "product_packaging_profiles",
        sa.Column("label_height_in", sa.Float(), nullable=False, server_default="2.1"),
    )
    op.add_column(
        "product_packaging_profiles",
        sa.Column("label_source_count", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("product_packaging_profiles", "label_source_count")
    op.drop_column("product_packaging_profiles", "label_height_in")
    op.drop_column("product_packaging_profiles", "label_width_in")
    op.drop_column("product_packaging_profiles", "label_layout")
