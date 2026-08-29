"""Add facility-scoped user permission overrides.

Revision ID: 0053_user_permission_overrides
Revises: 0052_storefront_studio
"""

from alembic import op
import sqlalchemy as sa


revision = "0053_user_permission_overrides"
down_revision = "0052_storefront_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_user_permission_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission", sa.String(120), nullable=False),
        sa.Column("effect", sa.String(12), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("effect in ('allow', 'deny')", name="ck_app_user_permission_effect"),
        sa.UniqueConstraint("user_id", "organization_id", "facility_id", "permission", name="uq_app_user_permission_scope"),
    )
    op.create_index("ix_app_user_permission_overrides_user_id", "app_user_permission_overrides", ["user_id"])
    op.create_index("ix_app_user_permission_overrides_organization_id", "app_user_permission_overrides", ["organization_id"])
    op.create_index("ix_app_user_permission_overrides_facility_id", "app_user_permission_overrides", ["facility_id"])
    op.create_index("ix_app_user_permission_overrides_permission", "app_user_permission_overrides", ["permission"])
    op.create_index("ix_app_user_permission_scope", "app_user_permission_overrides", ["organization_id", "facility_id", "user_id"])


def downgrade() -> None:
    op.drop_index("ix_app_user_permission_scope", table_name="app_user_permission_overrides")
    op.drop_index("ix_app_user_permission_overrides_permission", table_name="app_user_permission_overrides")
    op.drop_index("ix_app_user_permission_overrides_facility_id", table_name="app_user_permission_overrides")
    op.drop_index("ix_app_user_permission_overrides_organization_id", table_name="app_user_permission_overrides")
    op.drop_index("ix_app_user_permission_overrides_user_id", table_name="app_user_permission_overrides")
    op.drop_table("app_user_permission_overrides")
