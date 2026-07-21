"""Add facility crew availability."""
from alembic import op
from modules.coman.models import CrewAvailability
revision = "0006_crew_availability"
down_revision = "0005_production_actuals"
branch_labels = None
depends_on = None
def upgrade() -> None:
    CrewAvailability.__table__.create(bind=op.get_bind(), checkfirst=True)
    if op.get_bind().dialect.name == "postgresql": op.execute("alter table coman_crew_availability enable row level security")
def downgrade() -> None: op.drop_table("coman_crew_availability")
