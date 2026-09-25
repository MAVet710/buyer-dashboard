"""Add scoped work and durable recurring definitions. No domain records rewritten."""
from alembic import op
import sqlalchemy as sa

revision = "0080_doobie_work"
down_revision = "0079_security_observation"
branch_labels = None
depends_on = None


def common_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("assignee_id", sa.String(36), sa.ForeignKey("app_users.id", ondelete="RESTRICT")),
        *[sa.Column(key, sa.String(size), nullable=False) for key, size in
          (("entity_type", 80), ("entity_id", 255), ("workspace", 120), ("route", 1000), ("created_by", 36))],
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    ]


def upgrade():
    op.create_table("doobie_work_templates", *common_columns(),
        sa.Column("frequency", sa.String(16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("next_occurrence", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("frequency in ('daily','weekly','monthly')", name="ck_work_template_frequency"),
        sa.CheckConstraint("priority in ('low','medium','high','critical')", name="ck_work_template_priority"))
    op.create_index("ix_work_template_scope_active", "doobie_work_templates", ["organization_id", "facility_id", "active"])
    op.create_table("doobie_work_items", *common_columns(),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by", sa.String(36)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_reason", sa.String(2000), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("doobie_work_templates.id", ondelete="RESTRICT")),
        sa.Column("occurrence_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status in ('open','in_progress','blocked','completed')", name="ck_work_status"),
        sa.CheckConstraint("priority in ('low','medium','high','critical')", name="ck_work_priority"),
        sa.CheckConstraint("status != 'blocked' OR length(blocked_reason) > 0", name="ck_work_blocked"),
        sa.CheckConstraint("(status = 'completed' AND completed_at IS NOT NULL AND completed_by IS NOT NULL) OR (status != 'completed' AND completed_at IS NULL AND completed_by IS NULL)", name="ck_work_completion"),
        sa.UniqueConstraint("template_id", "occurrence_at", name="uq_work_occurrence"))
    op.create_index("ix_work_scope_status_due", "doobie_work_items", ["organization_id", "facility_id", "status", "due_at"])
    op.create_index("ix_work_scope_assignee_due", "doobie_work_items", ["organization_id", "facility_id", "assignee_id", "due_at"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("doobie_work_templates", "doobie_work_items"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            op.execute(f"""DO $$ DECLARE role_name text; BEGIN
              FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                  EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I',role_name);
                END IF;
              END LOOP;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
                GRANT SELECT, INSERT, UPDATE ON TABLE public.{table} TO doobielogic_render_runtime;
              END IF;
            END $$;""")


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(sa.text("LOCK TABLE doobie_work_items, doobie_work_templates IN ACCESS EXCLUSIVE MODE"))
    for name in ("doobie_work_items", "doobie_work_templates"):
        if connection.execute(sa.text(f"SELECT id FROM {name} LIMIT 1")).first():
            raise RuntimeError("Work records exist. Retain the additive schema and roll back application code only.")
    op.drop_table("doobie_work_items")
    op.drop_table("doobie_work_templates")
