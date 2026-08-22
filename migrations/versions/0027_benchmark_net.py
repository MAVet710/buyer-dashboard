"""Add privacy-safe benchmark network.

Revision ID: 0027_benchmark_net
Revises: 0026_doobie_actions
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_benchmark_net"
down_revision = "0026_doobie_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("share_anonymized_aggregates", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("minimum_cohort_size", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", name="uq_benchmark_setting_org"),
        sa.CheckConstraint("minimum_cohort_size >= 3 and minimum_cohort_size <= 50", name="ck_benchmark_min_cohort"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_benchmark_settings_organization_id", "benchmark_settings", ["organization_id"])

    op.create_table(
        "benchmark_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("cohort_key", sa.String(160), nullable=False, server_default="all"),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("facility_id","metric_key","cohort_key","period_start","period_end", name="uq_benchmark_observation_period"),
        sa.CheckConstraint("sample_count >= 1", name="ck_benchmark_sample_count"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_benchmark_observations_organization_id", "benchmark_observations", ["organization_id"])
    op.create_index("ix_benchmark_observations_facility_id", "benchmark_observations", ["facility_id"])
    op.create_index("ix_benchmark_metric_cohort_period", "benchmark_observations", ["metric_key","cohort_key","period_end"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE benchmark_settings ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE benchmark_observations ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("benchmark_observations")
    op.drop_table("benchmark_settings")
