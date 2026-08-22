"""Close remaining callable/default ACL paths behind FastAPI.

Revision ID: 0037_function_acl_hardening
Revises: 0036_supabase_data_api_hardening

Supabase-hosted projects keep platform-managed default ACLs for objects created
by ``supabase_admin``. The application migration role cannot rewrite another
role's defaults. Public Data API must therefore also be disabled at the Supabase
platform before cutover. This revision hardens every object/default privilege
that is owned by the application migration role (postgres).
"""

from alembic import op

revision = "0037_function_acl_hardening"
down_revision = "0036_supabase_data_api_hardening"
branch_labels = None
depends_on = None


HARDEN_SQL = r"""
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC;

DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', role_name);
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', role_name);
            EXECUTE format('REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', role_name);
        END IF;
    END LOOP;
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(HARDEN_SQL)


def downgrade() -> None:
    # Deliberately retain the least-privilege posture. Re-granting browser or
    # PUBLIC execution during rollback would reopen the Data API boundary.
    pass
