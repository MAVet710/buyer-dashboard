"""Add facility-scoped wholesale CRM without rewriting commercial ledgers."""
from alembic import op
import sqlalchemy as sa

revision = "0080_wholesale_crm"
down_revision = "0079_security_observation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE commercial_customer_relationships (
            status VARCHAR(24) NOT NULL,
            id VARCHAR(36) NOT NULL,
            organization_id VARCHAR(36) NOT NULL,
            facility_id VARCHAR(36) NOT NULL,
            partner_id VARCHAR(36) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            owner VARCHAR(255) NOT NULL,
            next_action VARCHAR(1000) NOT NULL,
            next_action_date DATE,
            PRIMARY KEY (id),
            CONSTRAINT uq_crm_account_scope UNIQUE (organization_id, facility_id, partner_id),
            CONSTRAINT ck_crm_account_status CHECK (status in ('prospect','active','on_hold','inactive')),
            FOREIGN KEY(organization_id) REFERENCES coman_organizations (id),
            FOREIGN KEY(facility_id) REFERENCES coman_facilities (id),
            FOREIGN KEY(partner_id) REFERENCES commercial_trade_partners (id)
        )
    """)
    op.execute("""
        CREATE TABLE commercial_opportunities (
            title VARCHAR(255) NOT NULL,
            stage VARCHAR(24) NOT NULL,
            estimated_value NUMERIC(14, 2) NOT NULL,
            expected_close_date DATE,
            source VARCHAR(255) NOT NULL,
            id VARCHAR(36) NOT NULL,
            organization_id VARCHAR(36) NOT NULL,
            facility_id VARCHAR(36) NOT NULL,
            partner_id VARCHAR(36) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            owner VARCHAR(255) NOT NULL,
            next_action VARCHAR(1000) NOT NULL,
            next_action_date DATE,
            PRIMARY KEY (id),
            CONSTRAINT ck_crm_opportunity_stage CHECK (stage in ('lead','qualified','quoted','negotiating','won','lost')),
            CONSTRAINT ck_crm_opportunity_value CHECK (estimated_value >= 0),
            FOREIGN KEY(organization_id) REFERENCES coman_organizations (id),
            FOREIGN KEY(facility_id) REFERENCES coman_facilities (id),
            FOREIGN KEY(partner_id) REFERENCES commercial_trade_partners (id)
        )
    """)
    op.execute('CREATE INDEX ix_crm_opportunity_scope_stage ON commercial_opportunities (organization_id, facility_id, stage, created_at)')
    op.execute("""
        CREATE TABLE commercial_activities (
            kind VARCHAR(24) NOT NULL,
            body TEXT NOT NULL,
            reference VARCHAR(255) NOT NULL,
            actor VARCHAR(255) NOT NULL,
            id VARCHAR(36) NOT NULL,
            organization_id VARCHAR(36) NOT NULL,
            facility_id VARCHAR(36) NOT NULL,
            partner_id VARCHAR(36) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT ck_crm_activity_kind CHECK (kind in ('call','email','meeting','note','task_reference')),
            FOREIGN KEY(organization_id) REFERENCES coman_organizations (id),
            FOREIGN KEY(facility_id) REFERENCES coman_facilities (id),
            FOREIGN KEY(partner_id) REFERENCES commercial_trade_partners (id)
        )
    """)
    op.execute('CREATE INDEX ix_crm_activity_timeline ON commercial_activities (organization_id, facility_id, partner_id, created_at)')
    op.execute("""
        CREATE TABLE commercial_quotes (
            title VARCHAR(255) NOT NULL,
            opportunity_id VARCHAR(36),
            commercial_order_id VARCHAR(36),
            status VARCHAR(24) NOT NULL,
            lines_json TEXT NOT NULL,
            created_by VARCHAR(255) NOT NULL,
            id VARCHAR(36) NOT NULL,
            organization_id VARCHAR(36) NOT NULL,
            facility_id VARCHAR(36) NOT NULL,
            partner_id VARCHAR(36) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT ck_crm_quote_status CHECK (status in ('draft','converted')),
            CONSTRAINT uq_crm_quote_order UNIQUE (commercial_order_id),
            FOREIGN KEY(opportunity_id) REFERENCES commercial_opportunities (id),
            FOREIGN KEY(commercial_order_id) REFERENCES commercial_orders (id),
            FOREIGN KEY(organization_id) REFERENCES coman_organizations (id),
            FOREIGN KEY(facility_id) REFERENCES coman_facilities (id),
            FOREIGN KEY(partner_id) REFERENCES commercial_trade_partners (id)
        )
    """)
    op.execute('CREATE INDEX ix_crm_quote_scope_customer ON commercial_quotes (organization_id, facility_id, partner_id, created_at)')
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            op.execute(f"""DO $$ DECLARE role_name text; BEGIN
                FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                        EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I', role_name);
                    END IF;
                END LOOP;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO doobielogic_render_runtime;
                END IF;
            END $$;""")


TABLES = ('commercial_customer_relationships', 'commercial_opportunities', 'commercial_activities', 'commercial_quotes')

def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        op.execute("SET LOCAL lock_timeout = '5s'")
        op.execute('LOCK TABLE ' + ', '.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE')
    for name in TABLES:
        if connection.execute(sa.text('SELECT id FROM ' + name + ' LIMIT 1')).first():
            raise RuntimeError('CRM records exist. Preserve evidence and use a reviewed rollback plan.')
    for name in reversed(TABLES):
        op.drop_table(name)
