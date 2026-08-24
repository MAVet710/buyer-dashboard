"""Expand integration providers for native AI runtime and Spacemail.

Revision ID: 0041_integration_providers
Revises: 0040_ai_runtime
"""

from alembic import op

revision = "0041_integration_providers"
down_revision = "0040_ai_runtime"
branch_labels = None
depends_on = None

NEW_CHECK = "provider in ('metrc','doobie','ai_runtime','spacemail')"
OLD_CHECK = "provider in ('metrc','doobie')"


def _replace_provider_check(expression: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE integration_configurations "
            "DROP CONSTRAINT IF EXISTS ck_integration_provider"
        )
        op.create_check_constraint(
            "ck_integration_provider",
            "integration_configurations",
            expression,
        )
        return

    with op.batch_alter_table("integration_configurations", recreate="always") as batch:
        batch.drop_constraint("ck_integration_provider", type_="check")
        batch.create_check_constraint("ck_integration_provider", expression)


def upgrade() -> None:
    _replace_provider_check(NEW_CHECK)


def downgrade() -> None:
    # The older schema cannot represent these platform integrations.
    op.execute(
        "delete from integration_configurations "
        "where provider in ('ai_runtime','spacemail')"
    )
    _replace_provider_check(OLD_CHECK)
