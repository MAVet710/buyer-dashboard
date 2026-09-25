"""Add durable planning documents linked to canonical production orders."""
from alembic import op
import sqlalchemy as sa

revision = "0082_white_label_execution"
down_revision = "0081_wholesale_crm"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("white_label_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id"), nullable=False),
        sa.Column("source_lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id"), nullable=False),
        sa.Column("production_order_id", sa.String(36), sa.ForeignKey("coman_production_orders.id"), unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *[sa.Column(key, sa.Text(), nullable=False) for key in ("scenario_json", "source_json", "economics_json")],
        *[sa.Column(key, sa.String(255), nullable=False) for key in ("created_by", "updated_by")],
        *[sa.Column(key, sa.DateTime(timezone=True), nullable=False) for key in ("created_at", "updated_at")],
        sa.CheckConstraint("status in ('draft','approved','cancelled')", name="ck_white_label_plan_status"))
    op.create_index("ix_white_label_plan_scope", "white_label_plans", ["organization_id", "facility_id", "updated_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.white_label_plans ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON TABLE public.white_label_plans FROM PUBLIC")
        op.execute("""DO $$ DECLARE role_name text; BEGIN
          FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
              EXECUTE format('REVOKE ALL ON TABLE public.white_label_plans FROM %I',role_name);
            END IF;
          END LOOP;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE public.white_label_plans TO doobielogic_render_runtime;
          END IF;
        END $$;""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '5s'")
        op.execute("LOCK TABLE white_label_plans IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text("SELECT 1 FROM white_label_plans LIMIT 1")).first():
        raise RuntimeError("Cannot discard saved White Label plans.")
    op.drop_table("white_label_plans")
