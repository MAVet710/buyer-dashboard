"""Enable explicit production onboarding and governed network-source metadata."""
from alembic import op
import sqlalchemy as sa

revision='0089_connected_onboarding'
down_revision='0088_cultivation_radio'
branch_labels=None
depends_on=None

OLD_MODES="mode in ('doobielogic_sandbox','metrc_sandbox')"
NEW_MODES="mode in ('doobielogic_sandbox','metrc_sandbox','metrc_production')"
OLD_PROVIDERS="provider in ('metrc','biotrack','quickbooks','doobie','ai_runtime','spacemail','metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')"
NEW_PROVIDERS=OLD_PROVIDERS[:-1]+",'cultivation_network')"
OLD_CONNECTION_MODES="mode = 'file' OR (mode = 'push' AND provider = 'json')"
NEW_CONNECTION_MODES=OLD_CONNECTION_MODES+" OR (mode = 'network' AND provider = 'json')"


def change(table, constraint, expression):
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(constraint,type_='check')
        batch.create_check_constraint(constraint,expression)


def upgrade():
    if op.get_bind().dialect.name=='postgresql':
        op.execute("SET LOCAL lock_timeout='5s'")
    change('alpha_operating_modes','ck_alpha_operating_mode_mode',NEW_MODES)
    change('integration_configurations','ck_integration_provider',NEW_PROVIDERS)
    change('cultivation_telemetry_connections','ck_ci_connection_mode',NEW_CONNECTION_MODES)


def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=='postgresql':
        op.execute("SET LOCAL lock_timeout='5s'")
        op.execute('LOCK TABLE alpha_operating_modes, integration_configurations, cultivation_telemetry_connections IN ACCESS EXCLUSIVE MODE')
    checks=("SELECT 1 FROM alpha_operating_modes WHERE mode='metrc_production' LIMIT 1",
            "SELECT 1 FROM integration_configurations WHERE provider='cultivation_network' LIMIT 1",
            "SELECT 1 FROM cultivation_telemetry_connections WHERE mode='network' LIMIT 1")
    if any(bind.execute(sa.text(sql)).first() for sql in checks):
        raise RuntimeError('Connected onboarding evidence exists. Preserve the additive schema.')
    change('cultivation_telemetry_connections','ck_ci_connection_mode',OLD_CONNECTION_MODES)
    change('integration_configurations','ck_integration_provider',OLD_PROVIDERS)
    change('alpha_operating_modes','ck_alpha_operating_mode_mode',OLD_MODES)
