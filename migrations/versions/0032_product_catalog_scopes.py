"""Add retail and production catalog scopes.

Revision ID: 0032_product_catalog_scopes
Revises: 0031_cultivation_plants
"""
import sqlalchemy as sa
from alembic import op

revision = "0032_product_catalog_scopes"
down_revision = "0031_cultivation_plants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_master_profiles", sa.Column("retail_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("product_master_profiles", sa.Column("production_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("product_master_profiles", "production_enabled")
    op.drop_column("product_master_profiles", "retail_enabled")
