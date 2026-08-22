"""Add durable cultivation plant inventory.

Revision ID: 0031_cultivation_plants
Revises: 0030_retail_sales_ledger
"""
from alembic import op
from modules.cultivation.models import CultivationPlant, CultivationPlantEvent

revision = "0031_cultivation_plants"
down_revision = "0030_retail_sales_ledger"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    CultivationPlant.__table__.create(bind=bind, checkfirst=True)
    CultivationPlantEvent.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table cultivation_plants enable row level security")
        op.execute("alter table cultivation_plant_events enable row level security")

def downgrade() -> None:
    op.drop_table("cultivation_plant_events")
    op.drop_table("cultivation_plants")
