"""Add physical dispatch runs and stop evidence without changing fulfillment."""
from alembic import op
import sqlalchemy as sa

revision = "0084_wholesale_logistics"
down_revision = "0083_onboarding_reporting"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("wholesale_dispatch_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id"), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("driver_name", sa.String(255)),
        sa.Column("driver_license_number", sa.String(128)),
        sa.Column("vehicle_make", sa.String(128)),
        sa.Column("vehicle_model", sa.String(128)),
        sa.Column("vehicle_license_plate_number", sa.String(64)),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_dispatch_scope_date", "wholesale_dispatch_runs", ["organization_id", "facility_id", "service_date"])
    op.create_table("wholesale_dispatch_stops",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("wholesale_dispatch_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("shipment_id", sa.String(36), sa.ForeignKey("commercial_shipments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_item_id", sa.String(36), sa.ForeignKey("doobie_work_items.id", ondelete="SET NULL")),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("planned_start", sa.DateTime(timezone=True)),
        sa.Column("planned_end", sa.DateTime(timezone=True)),
        sa.Column("address_snapshot", sa.Text(), nullable=False),
        sa.Column("contact_snapshot", sa.Text(), nullable=False),
        sa.Column("partner_name_snapshot", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float()), sa.Column("longitude", sa.Float()),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recipient_name", sa.String(255), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("outcome_notes", sa.Text(), nullable=False),
        sa.Column("acknowledgment_name", sa.String(255), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("shipment_id", name="uq_dispatch_shipment"),
        sa.CheckConstraint("status in ('planned','loaded','en_route','arrived','delivered','partial','rejected','returned')", name="ck_dispatch_stop_status"),
        sa.CheckConstraint("sequence > 0", name="ck_dispatch_sequence"),
        sa.CheckConstraint("(latitude is null and longitude is null) or (latitude is not null and longitude is not null and latitude between -90 and 90 and longitude between -180 and 180)", name="ck_dispatch_coordinates"))
    op.create_index("ix_dispatch_stop_run_sequence", "wholesale_dispatch_stops", ["run_id", "sequence"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("wholesale_dispatch_runs", "wholesale_dispatch_stops"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            op.execute(f"""DO $$ DECLARE role_name text; BEGIN
                FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                        EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I',role_name);
                    END IF;
                END LOOP;
            END $$;""")
        # Match operational migrations: reuse the existing server identity only.
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.wholesale_dispatch_runs,
                    public.wholesale_dispatch_stops TO doobielogic_render_runtime;
            END IF;
        END $$;""")


def downgrade():
    """Only unused dispatch tables may be removed; preserve all physical evidence."""
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        # Keep both locks through the checks and drops to exclude concurrent writes.
        connection.execute(sa.text("LOCK TABLE public.wholesale_dispatch_runs, "
                                   "public.wholesale_dispatch_stops IN ACCESS EXCLUSIVE MODE"))
    elif connection.dialect.name != "sqlite":
        raise RuntimeError("Unsupported database for dispatch evidence rollback.")
    for name in ("wholesale_dispatch_runs", "wholesale_dispatch_stops"):
        table = sa.table(name, sa.column("id"))
        if connection.execute(sa.select(table.c.id).limit(1)).first() is not None:
            raise RuntimeError("Dispatch records exist. Preserve evidence and review a separate rollback plan; no tables were dropped.")
    op.drop_table("wholesale_dispatch_stops")
    op.drop_table("wholesale_dispatch_runs")
