"""Add room-scoped environmental evidence and operator targets.

Additive release: no existing operational data is rewritten. Browser roles have
no access; the existing server runtime uses the same tenant claims as cultivation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0085_cultivation_telemetry"
down_revision = "0084_wholesale_logistics"
branch_labels = None
depends_on = None

TABLES = ("cultivation_environment_observations", "cultivation_environment_targets")


def scope_columns():
    return [sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), nullable=False),
            sa.Column("facility_id", sa.String(36), nullable=False),
            sa.Column("room_id", sa.String(36), nullable=False),
            sa.Column("metric", sa.String(40), nullable=False)]


def room_fk():
    return sa.ForeignKeyConstraint(["organization_id", "facility_id", "room_id"],
        ["cultivation_rooms.organization_id", "cultivation_rooms.facility_id", "cultivation_rooms.id"], ondelete="RESTRICT")


def upgrade():
    with op.batch_alter_table("cultivation_rooms") as batch:
        batch.create_unique_constraint("uq_cultivation_room_scope", ["organization_id", "facility_id", "id"])
    op.create_table(TABLES[0], *scope_columns(),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("event_id", sa.String(120), nullable=False),
        sa.Column("device_id", sa.String(120), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False), room_fk(),
        sa.UniqueConstraint("organization_id", "facility_id", "room_id", "source", "event_id", "metric", "device_id", name="uq_cultivation_environment_event"),
        sa.CheckConstraint("quality in ('valid','suspect','invalid')", name="ck_environment_quality"))
    op.create_index("ix_environment_room_time", TABLES[0], ["organization_id", "facility_id", "room_id", "observed_at"])
    op.create_index("ix_environment_stream_time", TABLES[0], ["room_id", "metric", "source", "device_id", "observed_at"])
    op.create_table(TABLES[1], *scope_columns(),
        sa.Column("minimum", sa.Float(), nullable=True), sa.Column("maximum", sa.Float(), nullable=True),
        sa.Column("stale_minutes", sa.Integer(), nullable=False), room_fk(),
        sa.UniqueConstraint("room_id", "metric", name="uq_environment_target_room_metric"),
        sa.CheckConstraint("minimum IS NULL OR maximum IS NULL OR minimum <= maximum", name="ck_environment_target_range"),
        sa.CheckConstraint("stale_minutes >= 1 AND stale_minutes <= 10080", name="ck_environment_target_stale"))
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            op.execute(f"""DO $$ DECLARE role_name text; BEGIN
              FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                  EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I',role_name);
                END IF;
              END LOOP;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
                REVOKE ALL ON TABLE public.{table} FROM doobielogic_render_runtime;
                GRANT SELECT, INSERT{', UPDATE' if table == TABLES[1] else ''} ON TABLE public.{table} TO doobielogic_render_runtime;
              END IF;
            END $$;""")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '5s'")
        op.execute(f"LOCK TABLE {', '.join(TABLES)} IN ACCESS EXCLUSIVE MODE")
    for table in TABLES:
        if bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("Telemetry evidence or targets exist. Preserve data and review a separate rollback plan.")
    for table in reversed(TABLES):
        op.drop_table(table)
    with op.batch_alter_table("cultivation_rooms") as batch:
        batch.drop_constraint("uq_cultivation_room_scope", type_="unique")
