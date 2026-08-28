"""Add menu image URLs to product master profiles.

Revision ID: 0049_product_menu_images
Revises: 0048_commerce_storefronts
"""

from alembic import op
import sqlalchemy as sa


revision = "0049_product_menu_images"
down_revision = "0048_commerce_storefronts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("product_master_profiles") as batch:
        batch.add_column(sa.Column("image_url", sa.String(1024), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("product_master_profiles") as batch:
        batch.drop_column("image_url")
