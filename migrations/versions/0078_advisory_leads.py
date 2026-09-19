"""Durable platform-owned advisory leads and consented daily event totals.

Revision ID: 0078_advisory_leads
Revises: 0077_dev_reference_metrc_tags
"""
from alembic import op
import sqlalchemy as sa

revision = '0078_advisory_leads'
down_revision = '0077_dev_reference_metrc_tags'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('advisory_leads',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('coman_organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('submission_id', sa.String(36), nullable=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('phone', sa.String(40), nullable=False, server_default=''),
        sa.Column('company', sa.String(160), nullable=False),
        sa.Column('role', sa.String(120), nullable=False),
        sa.Column('state', sa.String(80), nullable=False),
        sa.Column('operation', sa.String(120), nullable=False),
        sa.Column('locations', sa.Integer(), nullable=False),
        sa.Column('challenge', sa.String(2000), nullable=False),
        sa.Column('service', sa.String(80), nullable=False),
        sa.Column('message', sa.Text(), nullable=False, server_default=''),
        sa.Column('consent', sa.Boolean(), nullable=False),
        sa.Column('consent_version', sa.String(32), nullable=False, server_default='advisory-intake-v1'),
        sa.Column('source_tool', sa.String(64), nullable=False, server_default=''),
        sa.Column('score_summary_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('attribution_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(24), nullable=False, server_default='NEW'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status in ('NEW','CONTACTED','QUALIFIED','CONSULTATION_BOOKED','PROPOSAL_SENT','CLIENT','CLOSED_LOST')", name='ck_advisory_lead_status'),
        sa.CheckConstraint('locations >= 1 AND locations <= 10000', name='ck_advisory_lead_locations'),
        sa.UniqueConstraint('organization_id', 'submission_id', name='uq_advisory_lead_submission'),
    )
    op.create_index('ix_advisory_lead_owner_status_created', 'advisory_leads', ['organization_id', 'status', 'created_at'])
    op.create_table('advisory_daily_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('coman_organizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('event', sa.String(64), nullable=False),
        sa.Column('placement', sa.String(40), nullable=False),
        sa.Column('item', sa.String(64), nullable=False, server_default=''),
        sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('organization_id', 'day', 'event', 'placement', 'item', name='uq_advisory_daily_event'),
    )
    if op.get_bind().dialect.name == 'postgresql':
        for table in ('advisory_leads', 'advisory_daily_events'):
            op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL ON TABLE public.{table} FROM PUBLIC')
            op.execute(f"""DO $$ DECLARE role_name text; BEGIN
              FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                  EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I', role_name);
                END IF;
              END LOOP;
            END $$;""")


def downgrade():
    op.drop_table('advisory_daily_events')
    op.drop_index('ix_advisory_lead_owner_status_created', table_name='advisory_leads')
    op.drop_table('advisory_leads')
