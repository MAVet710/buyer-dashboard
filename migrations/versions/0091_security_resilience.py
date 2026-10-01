"""Security monitor recovery intelligence and perimeter source state.

Revision ID: 0091_security_resilience
Revises: 0090_security_guard
"""
from alembic import op
import sqlalchemy as sa

revision = "0091_security_resilience"
down_revision = "0090_security_guard"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout='5s'")
    with op.batch_alter_table("security_events") as batch:
        batch.alter_column("actor_id", existing_type=sa.String(36), type_=sa.String(64),
                           existing_nullable=False)
    with op.batch_alter_table("security_incidents") as batch:
        batch.add_column(sa.Column("recovered_at", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("recovery_json", sa.Text(), nullable=False, server_default="{}"))
    with op.batch_alter_table("security_monitor_state") as batch:
        batch.add_column(sa.Column("last_error_category", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("last_error_at", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("clean_cycles", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "security_source_state",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("checked_at", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("cursor", sa.String(160), nullable=False, server_default=""),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_category", sa.String(64), nullable=False, server_default=""),
        sa.Column("last_event_at", sa.Float(), nullable=False, server_default="0"),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
    )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE public.security_source_state ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON TABLE public.security_source_state FROM PUBLIC")
        op.execute("""DO $$ DECLARE role_name text; BEGIN
          FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
              EXECUTE format('REVOKE ALL ON TABLE public.security_source_state FROM %I', role_name);
            END IF;
          END LOOP;
        END $$;""")
        op.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE public.security_source_state TO doobielogic_render_runtime;
            GRANT UPDATE (recovered_at,recovery_json,status,version,evidence_json,last_seen,occurrences)
              ON public.security_incidents TO doobielogic_render_runtime;
            GRANT UPDATE (checked_at,status,dropped,failures,last_error_category,last_error_at,clean_cycles)
              ON public.security_monitor_state TO doobielogic_render_runtime;
          END IF;
        END $$;""")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("SET LOCAL lock_timeout='5s'"))
        bind.execute(sa.text(
            "LOCK TABLE public.security_source_state, public.security_incidents, "
            "public.security_monitor_state IN ACCESS EXCLUSIVE MODE"
        ))
    elif bind.dialect.name != "sqlite":
        raise RuntimeError("Unsupported database for security resilience rollback.")
    source = sa.table("security_source_state", sa.column("id"))
    if bind.execute(sa.select(source.c.id).limit(1)).first() is not None:
        raise RuntimeError("Security source evidence exists. Preserve the additive schema.")
    events = sa.table("security_events", sa.column("id"), sa.column("actor_id"))
    if bind.execute(sa.select(events.c.id).where(sa.func.length(events.c.actor_id) > 36).limit(1)).first() is not None:
        raise RuntimeError("Known-account security evidence requires the widened identity column. Preserve the additive schema.")
    incidents = sa.table("security_incidents", sa.column("id"), sa.column("recovered_at"), sa.column("recovery_json"))
    if bind.execute(sa.select(incidents.c.id).where(
        (incidents.c.recovered_at != 0) | (incidents.c.recovery_json != "{}")
    ).limit(1)).first() is not None:
        raise RuntimeError("Security recovery evidence exists. Preserve the additive schema.")
    monitor = sa.table("security_monitor_state", sa.column("id"), sa.column("last_error_category"),
                       sa.column("last_error_at"), sa.column("clean_cycles"))
    if bind.execute(sa.select(monitor.c.id).where(
        (monitor.c.last_error_category != "") | (monitor.c.last_error_at != 0) | (monitor.c.clean_cycles != 0)
    ).limit(1)).first() is not None:
        raise RuntimeError("Security monitor recovery evidence exists. Preserve the additive schema.")
    op.drop_table("security_source_state")
    with op.batch_alter_table("security_events") as batch:
        batch.alter_column("actor_id", existing_type=sa.String(64), type_=sa.String(36),
                           existing_nullable=False)
    with op.batch_alter_table("security_monitor_state") as batch:
        batch.drop_column("clean_cycles")
        batch.drop_column("last_error_at")
        batch.drop_column("last_error_category")
    with op.batch_alter_table("security_incidents") as batch:
        batch.drop_column("recovery_json")
        batch.drop_column("recovered_at")
