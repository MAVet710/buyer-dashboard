"""Add production actual performance records."""
from alembic import op
from modules.coman.models import ProductionActual
revision = "0005_production_actuals"
down_revision = "0004_hand_labor_areas"
branch_labels = None
depends_on = None
def upgrade() -> None:
    ProductionActual.__table__.create(bind=op.get_bind(), checkfirst=True)
    if op.get_bind().dialect.name == "postgresql": op.execute("alter table coman_production_actuals enable row level security")
def downgrade() -> None: op.drop_table("coman_production_actuals")
