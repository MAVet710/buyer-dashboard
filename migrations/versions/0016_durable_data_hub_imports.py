"""Add tenant-scoped, versioned Data Hub source storage.

Revision ID: 0016_durable_data_hub_imports
Revises: 0015_inventory_audit_lifecycle
"""

from alembic import op

from modules.coman.models import DataHubImport

revision = "0016_durable_data_hub_imports"
down_revision = "0015_inventory_audit_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    DataHubImport.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table data_hub_imports enable row level security")


def downgrade() -> None:
    op.drop_table("data_hub_imports")
