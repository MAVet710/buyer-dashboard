"""Add facility readiness annotations and scheduled report delivery receipts."""
from alembic import op
import sqlalchemy as sa

revision = "0083_onboarding_reporting"
down_revision = "0082_white_label_execution"
branch_labels = None
depends_on = None
TABLES = ("facility_readiness_annotations", "report_subscriptions", "report_deliveries")


def _scope():
    return [sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False)]


def upgrade():
    op.create_table(TABLES[0], *_scope(),
        sa.Column("item_key", sa.String(40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("app_users.id", ondelete="SET NULL")),
        sa.Column("work_item_id", sa.String(36), sa.ForeignKey("doobie_work_items.id", ondelete="SET NULL")),
        sa.Column("target_date", sa.Date()),
        sa.Column("manual_status", sa.String(24)),
        sa.Column("updated_by", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "facility_id", "item_key", name="uq_readiness_item"),
        sa.CheckConstraint("manual_status IS NULL OR manual_status IN ('complete','incomplete','not_applicable','needs_review')", name="ck_readiness_manual_status"))
    op.create_table(TABLES[1], *_scope(),
        sa.Column("report_type", sa.String(40), nullable=False),
        sa.Column("recipients_json", sa.Text(), nullable=False),
        sa.Column("cadence", sa.String(12), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cadence IN ('daily','weekly','monthly')", name="ck_report_subscription_cadence"))
    op.create_index("ix_report_subscription_due", TABLES[1], ["organization_id", "facility_id", "active", "next_run"])
    op.create_table(TABLES[2], *_scope(),
        sa.Column("subscription_id", sa.String(36), sa.ForeignKey("report_subscriptions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("recipients_json", sa.Text(), nullable=False),
        sa.Column("report_type", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("subscription_id", "run_key", name="uq_report_delivery_run"),
        sa.CheckConstraint("status IN ('processing','deferred','failed','sent','needs_review')", name="ck_report_delivery_status"))
    op.create_index("ix_report_delivery_history", TABLES[2], ["organization_id", "facility_id", "created_at"])
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
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO doobielogic_render_runtime;
              END IF;
            END $$;""")


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(sa.text("LOCK TABLE " + ", ".join(TABLES) + " IN ACCESS EXCLUSIVE MODE"))
    for table in TABLES:
        if connection.execute(sa.select(sa.column("id")).select_from(sa.table(table)).limit(1)).first():
            raise RuntimeError("Readiness or delivery records exist. Preserve evidence before rollback.")
    for table in reversed(TABLES):
        op.drop_table(table)
