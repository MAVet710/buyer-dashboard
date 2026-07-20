"""Add the platform-wide Level DEV role.

Revision ID: 0003_level_dev
Revises: 0002_app_users
"""

from __future__ import annotations

from alembic import op

revision = "0003_level_dev"
down_revision = "0002_app_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_app_user_facility_role", "app_user_facility_roles", type_="check")
        op.drop_constraint("ck_app_users_role", "app_users", type_="check")
        op.create_check_constraint(
            "ck_app_users_role", "app_users",
            "role in ('dev', 'admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')",
        )
        op.create_check_constraint(
            "ck_app_user_facility_role", "app_user_facility_roles",
            "role in ('dev', 'admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')",
        )
    else:
        with op.batch_alter_table("app_users") as batch:
            batch.drop_constraint("ck_app_users_role", type_="check")
            batch.create_check_constraint(
                "ck_app_users_role",
                "role in ('dev', 'admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')",
            )
    op.execute(
        "update app_users set role = 'dev', organization_id = null, updated_by = '0003_level_dev' "
        "where normalized_username = 'god'"
    )


def downgrade() -> None:
    op.execute("update app_users set role = 'admin' where role = 'dev'")
