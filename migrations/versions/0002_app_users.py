"""Add durable application users and facility roles.

Revision ID: 0002_app_users
Revises: 0001_coman_foundation
"""

from __future__ import annotations

from alembic import op

from modules.coman.models import AppUser, AppUserFacilityRole

revision = "0002_app_users"
down_revision = "0001_coman_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    AppUser.__table__.create(bind=bind, checkfirst=True)
    AppUserFacilityRole.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table app_users enable row level security")
        op.execute("alter table app_user_facility_roles enable row level security")


def downgrade() -> None:
    op.drop_table("app_user_facility_roles")
    op.drop_table("app_users")
