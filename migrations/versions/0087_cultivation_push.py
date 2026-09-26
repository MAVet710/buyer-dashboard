"""Add exact cultivation ingress grants; preserve all previous evidence."""
from alembic import op
import sqlalchemy as sa

revision = '0087_cultivation_push'
down_revision = '0086_cultivation_intelligence'
branch_labels = None
depends_on = None

TABLE = 'cultivation_ingress_grants'
CONNECTION = 'cultivation_telemetry_connections'


def upgrade():
    bind=op.get_bind()
    if bind.dialect.name=='postgresql':op.execute("SET LOCAL lock_timeout = '5s'")
    indexes={i['name']:i for i in sa.inspect(bind).get_indexes('service_accounts')}
    name='uq_cp_service_account_scope'
    if name not in indexes:
        op.create_index(name,'service_accounts',['organization_id','facility_id','id'],unique=True)
    elif not indexes[name]['unique'] or indexes[name]['column_names']!=['organization_id','facility_id','id']:
        raise RuntimeError('Incompatible service-account scope index.')
    with op.batch_alter_table(CONNECTION) as batch:
        batch.drop_constraint('ck_ci_connection_mode',type_='check')
        batch.create_check_constraint('ck_ci_connection_mode',"mode = 'file' OR (mode = 'push' AND provider = 'json')")
        batch.add_column(sa.Column('expected_interval_seconds',sa.Integer(),nullable=True))
        batch.add_column(sa.Column('stale_after_seconds',sa.Integer(),nullable=True))
        batch.create_check_constraint('ck_cp_expected_interval','expected_interval_seconds IS NULL OR expected_interval_seconds BETWEEN 1 AND 2678400')
        batch.create_check_constraint('ck_cp_stale_after','stale_after_seconds IS NULL OR stale_after_seconds BETWEEN 1 AND 2678400')
    op.create_table(TABLE,
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),nullable=False),
        sa.Column('facility_id',sa.String(36),nullable=False),
        sa.Column('connection_id',sa.String(36),nullable=False),
        sa.Column('service_account_id',sa.String(36),nullable=False),
        sa.Column('label',sa.String(120),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('revoked_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('created_by',sa.String(36),nullable=False),
        sa.Column('revoked_by',sa.String(36),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['organization_id','facility_id','connection_id'],[CONNECTION+'.organization_id',CONNECTION+'.facility_id',CONNECTION+'.id'],name='fk_ci_connection_id_telemetry_connections',ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['organization_id','facility_id','service_account_id'],['service_accounts.organization_id','service_accounts.facility_id','service_accounts.id'],name='fk_cp_grant_account_scope',ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'],['app_users.id'],name='fk_cp_grant_actor',ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['revoked_by'],['app_users.id'],name='fk_cp_grant_revoker',ondelete='RESTRICT'),
        sa.UniqueConstraint('service_account_id',name='uq_cp_grant_account'))
    op.create_index('ix_cp_grant_connection',TABLE,['organization_id','facility_id','connection_id'])
    if bind.dialect.name=='postgresql':
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
            GRANT UPDATE (version,revoked_at,revoked_by,updated_at) ON public.{TABLE} TO doobielogic_render_runtime;
            CREATE POLICY cp_server_runtime ON public.{TABLE} TO doobielogic_render_runtime USING (true) WITH CHECK (true);
          END IF;
        END $$;""")


def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=='postgresql':
        op.execute("SET LOCAL lock_timeout = '5s'")
        op.execute(f'LOCK TABLE {TABLE}, {CONNECTION} IN ACCESS EXCLUSIVE MODE')
    if bind.execute(sa.text(f'SELECT 1 FROM {TABLE} LIMIT 1')).first() or bind.execute(sa.text(f"SELECT 1 FROM {CONNECTION} WHERE mode='push' OR expected_interval_seconds IS NOT NULL OR stale_after_seconds IS NOT NULL LIMIT 1")).first():
        raise RuntimeError('Cultivation push evidence exists; preserve it before rollback.')
    op.drop_table(TABLE)
    with op.batch_alter_table(CONNECTION) as batch:
        batch.drop_constraint('ck_ci_connection_mode',type_='check')
        batch.create_check_constraint('ck_ci_connection_mode',"mode = 'file'")
        batch.drop_constraint('ck_cp_expected_interval',type_='check')
        batch.drop_constraint('ck_cp_stale_after',type_='check')
        batch.drop_column('expected_interval_seconds')
        batch.drop_column('stale_after_seconds')
    op.drop_index('uq_cp_service_account_scope',table_name='service_accounts')
