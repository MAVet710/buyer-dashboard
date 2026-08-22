"""Keep operational tables private behind the FastAPI authorization layer.

Revision ID: 0036_supabase_data_api_hardening
Revises: 0035_facility_capabilities
"""

from alembic import op

revision = "0036_supabase_data_api_hardening"
down_revision = "0035_facility_capabilities"
branch_labels = None
depends_on = None


HARDEN_SQL = r"""
DO $$
DECLARE
    table_record record;
    role_name text;
BEGIN
    FOR table_record IN
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname = 'public' AND tablename <> 'alembic_version'
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', table_record.schemaname, table_record.tablename);
    END LOOP;

    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', role_name);
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', role_name);
        END IF;
    END LOOP;
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(HARDEN_SQL)


def downgrade() -> None:
    # Deliberately retain the least-privilege posture. Restoring broad Data API
    # grants during rollback would expose operational data outside FastAPI.
    pass
