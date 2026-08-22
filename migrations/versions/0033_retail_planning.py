"""Add durable retail planning policies.

Revision ID: 0033_retail_planning
Revises: 0032_product_catalog_scopes
"""
from alembic import op
from modules.retail_planning.models import RetailPlanningPolicy

revision = "0033_retail_planning"
down_revision = "0032_product_catalog_scopes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind(); RetailPlanningPolicy.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql": op.execute("alter table retail_planning_policies enable row level security")

def downgrade() -> None: op.drop_table("retail_planning_policies")
