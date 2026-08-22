"""Add durable facility license and workspace capabilities.

Revision ID: 0035_facility_capabilities
Revises: 0034_integrations
"""

from alembic import op
import sqlalchemy as sa

revision = "0035_facility_capabilities"
down_revision = "0034_integrations"
branch_labels = None
depends_on = None


CAPABILITY_COLUMNS = (
    ("license_number", sa.Column("license_number", sa.String(160), nullable=False, server_default="")),
    ("license_type", sa.Column("license_type", sa.String(120), nullable=False, server_default="")),
    ("retail_enabled", sa.Column("retail_enabled", sa.Boolean(), nullable=False, server_default=sa.true())),
    ("production_enabled", sa.Column("production_enabled", sa.Boolean(), nullable=False, server_default=sa.true())),
    ("cultivation_enabled", sa.Column("cultivation_enabled", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("commercial_enabled", sa.Column("commercial_enabled", sa.Boolean(), nullable=False, server_default=sa.true())),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("coman_facilities")}
    for name, column in CAPABILITY_COLUMNS:
        if name not in existing:
            op.add_column("coman_facilities", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("coman_facilities")}
    for name, _ in reversed(CAPABILITY_COLUMNS):
        if name in existing:
            op.drop_column("coman_facilities", name)
