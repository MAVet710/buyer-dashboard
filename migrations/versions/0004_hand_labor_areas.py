"""Add universal facility hand-labor areas."""
from alembic import op
from modules.coman.models import HandLaborArea
revision = "0004_hand_labor_areas"
down_revision = "0003_level_dev"
branch_labels = None
depends_on = None
def upgrade() -> None:
    HandLaborArea.__table__.create(bind=op.get_bind(), checkfirst=True)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("alter table coman_hand_labor_areas enable row level security")
def downgrade() -> None:
    op.drop_table("coman_hand_labor_areas")
