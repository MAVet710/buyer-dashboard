"""Add encrypted integration configuration storage.

Revision ID: 0034_integrations
Revises: 0033_retail_planning
"""
from alembic import op
from modules.integrations.models import IntegrationConfiguration

revision = "0034_integrations"
down_revision = "0033_retail_planning"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind(); IntegrationConfiguration.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql": op.execute("alter table integration_configurations enable row level security")

def downgrade() -> None: op.drop_table("integration_configurations")
