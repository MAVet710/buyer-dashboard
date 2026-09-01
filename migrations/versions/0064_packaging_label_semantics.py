"""Add packaging-owned warning text for Label Studio.

Revision ID: 0064_packaging_label_semantics
Revises: 0063_structured_coa_documents
"""

import sqlalchemy as sa
from alembic import op

revision = "0064_packaging_label_semantics"
down_revision = "0063_structured_coa_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("product_packaging_profiles") as batch:
        batch.add_column(sa.Column("warning_text", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("product_packaging_profiles") as batch:
        batch.drop_column("warning_text")
