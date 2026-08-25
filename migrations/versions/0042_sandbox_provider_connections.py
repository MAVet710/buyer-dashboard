"""Allow isolated sandbox provider connection records.

Revision ID: 0042_sandbox_provider_connections
Revises: 0041_integration_providers
"""

from alembic import op

revision = "0042_sandbox_provider_connections"
down_revision = "0041_integration_providers"
branch_labels = None
depends_on = None

NEW_CHECK = (
    "provider in ('metrc','doobie','ai_runtime','spacemail',"
    "'metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')"
)
OLD_CHECK = "provider in ('metrc','doobie','ai_runtime','spacemail')"
SANDBOX_PROVIDERS = (
    "metrc_sandbox",
    "dutchie_sandbox",
    "biotrack_sandbox",
    "quickbooks_sandbox",
)


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
    quoted = ",".join(f"'{provider}'" for provider in SANDBOX_PROVIDERS)
    op.execute(f"delete from integration_configurations where provider in ({quoted})")
    _replace_provider_check(OLD_CHECK)
