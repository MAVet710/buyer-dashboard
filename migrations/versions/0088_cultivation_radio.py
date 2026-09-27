"""Explicit owned-sensor radio bindings. Discovery never writes telemetry here."""
from alembic import op
import sqlalchemy as sa

revision = '0088_cultivation_radio'
down_revision = '0087_cultivation_push'
branch_labels = None
depends_on = None
TABLE = 'cultivation_radio_bindings'
INDEX = 'uq_radio_device_connection_scope'

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("SET LOCAL lock_timeout='5s'")
    op.create_index(INDEX, 'cultivation_devices', ['organization_id','facility_id','id','connection_id'], unique=True)
    op.create_table(TABLE,
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), nullable=False),
        sa.Column('facility_id', sa.String(36), nullable=False),
        sa.Column('receiver_id', sa.String(32), nullable=False),
        sa.Column('source_address', sa.String(120), nullable=False),
        sa.Column('profile_id', sa.String(32), nullable=False),
        sa.Column('connection_id', sa.String(36), nullable=False),
        sa.Column('device_id', sa.String(36), nullable=False),
        sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('authorized_by', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('enabled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id','facility_id'], ['coman_facilities.organization_id','coman_facilities.id'], name='fk_radio_facility', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['organization_id','facility_id','connection_id'], ['cultivation_telemetry_connections.organization_id','cultivation_telemetry_connections.facility_id','cultivation_telemetry_connections.id'], name='fk_radio_connection', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['organization_id','facility_id','device_id','connection_id'], ['cultivation_devices.organization_id','cultivation_devices.facility_id','cultivation_devices.id','cultivation_devices.connection_id'], name='fk_radio_device_connection', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['app_users.id'], name='fk_radio_actor', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['authorized_by'], ['app_users.id'], name='fk_radio_authorizer', ondelete='RESTRICT'),
        sa.UniqueConstraint('organization_id','facility_id','receiver_id','source_address', name='uq_radio_source'),
        sa.UniqueConstraint('connection_id', name='uq_radio_connection'),
        sa.UniqueConstraint('organization_id','facility_id','id', name='uq_radio_binding_scope'),
        sa.CheckConstraint("profile_id IN ('bthome_v2','ambient_wh31')", name='ck_radio_profile'),
        sa.CheckConstraint('version >= 1', name='ck_radio_version'))
    if bind.dialect.name == 'postgresql':
        op.execute(f'ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public.{TABLE} FROM PUBLIC')
        op.execute(f"""DO $$ DECLARE role_name text; BEGIN
          FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
              EXECUTE format('REVOKE ALL ON TABLE public.{TABLE} FROM %I',role_name);
            END IF;
          END LOOP;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
            REVOKE ALL ON TABLE public.{TABLE} FROM doobielogic_render_runtime;
            GRANT SELECT, INSERT ON TABLE public.{TABLE} TO doobielogic_render_runtime;
            GRANT UPDATE (active,version,enabled_at,authorized_by) ON public.{TABLE} TO doobielogic_render_runtime;
            CREATE POLICY radio_server_runtime ON public.{TABLE} TO doobielogic_render_runtime USING (true) WITH CHECK (true);
          END IF;
        END $$;""")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("SET LOCAL lock_timeout='5s'")
        op.execute(f'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE')
    if bind.execute(sa.text(f'SELECT 1 FROM {TABLE} LIMIT 1')).first():
        raise RuntimeError('Radio approval evidence exists; preserve the additive schema.')
    op.drop_table(TABLE)
    op.drop_index(INDEX, table_name='cultivation_devices')
