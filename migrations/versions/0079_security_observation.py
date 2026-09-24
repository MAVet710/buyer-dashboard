"""Add platform-only alert observation tables. No business data is rewritten."""
from alembic import op
import sqlalchemy as sa

revision = "0079_security_observation"
down_revision = "0078_advisory_leads"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("security_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("occurred_at", sa.Float(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        *[sa.Column(k, sa.String(n), nullable=False, server_default="") for k,n in
          (("subject_key",64),("source_key",64),("actor_id",36),("organization_id",36),
           ("route",200),("request_id",36),("audit_id",36))])
    op.create_index("ix_security_event_kind_time_subject", "security_events", ["kind","occurred_at","subject_key"])
    op.create_index("ix_security_event_time", "security_events", ["occurred_at"])
    op.create_table("security_incidents",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("fingerprint",sa.String(64),nullable=False,unique=True),
        sa.Column("rule",sa.String(40),nullable=False),
        sa.Column("severity",sa.String(12),nullable=False),
        sa.Column("title",sa.String(160),nullable=False),
        sa.Column("group_key",sa.String(64),nullable=False),
        sa.Column("first_seen",sa.Float(),nullable=False),
        sa.Column("last_seen",sa.Float(),nullable=False),
        sa.Column("occurrences",sa.Integer(),nullable=False),
        sa.Column("status",sa.String(20),nullable=False,server_default="open"),
        sa.Column("version",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("evidence_json",sa.Text(),nullable=False,server_default="{}"),
        sa.Column("notification_status",sa.String(24),nullable=False,server_default="pending"),
        sa.Column("notification_updated_at",sa.Float(),nullable=False,server_default="0"),
        sa.Column("notification_reference",sa.String(120),nullable=False,server_default=""),
        sa.Column("notification_attempts",sa.Integer(),nullable=False,server_default="0"))
    op.create_index("ix_security_incident_time","security_incidents",["last_seen"])
    op.create_index("ix_security_incident_notification","security_incidents",["notification_status","notification_updated_at"])
    op.create_table("security_monitor_state",sa.Column("id",sa.String(80),primary_key=True),
        sa.Column("checked_at",sa.Float(),nullable=False),sa.Column("status",sa.String(32),nullable=False),
        sa.Column("dropped",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("failures",sa.Integer(),nullable=False,server_default="0"))
    if op.get_bind().dialect.name == "postgresql":
        for table in ("security_events","security_incidents","security_monitor_state"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            op.execute(f"""DO $$ DECLARE role_name text; BEGIN
              FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                  EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I',role_name);
                END IF;
              END LOOP;
            END $$;""")


    if op.get_bind().dialect.name == "postgresql":
        # Reuse the already deployed least-privilege runtime identity; no role or
        # membership changes. Browser roles remain revoked above.
        op.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.security_events,
              public.security_incidents, public.security_monitor_state TO doobielogic_render_runtime;
          END IF;
        END $$;""")


def downgrade():
    """Only an unused migration is reversible; never discard recorded evidence."""
    connection = op.get_bind()
    tables = ("security_events", "security_incidents", "security_monitor_state")
    if connection.dialect.name == "postgresql":
        # Hold locks through both the emptiness check and DDL to prevent a
        # concurrent observer from committing records between check and drop.
        connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(sa.text("LOCK TABLE public.security_events, public.security_incidents, "
                                   "public.security_monitor_state IN ACCESS EXCLUSIVE MODE"))
    elif connection.dialect.name != "sqlite":
        raise RuntimeError("Unsupported database for security evidence rollback.")
    for name in tables:
        table = sa.table(name, sa.column("id"))
        if connection.execute(sa.select(table.c.id).limit(1)).first() is not None:
            raise RuntimeError("Security records exist. Preserve/export evidence and review a separate rollback plan; no tables were dropped.")
    # All three checks complete before any table is removed.
    for name in reversed(tables):
        op.drop_table(name)
