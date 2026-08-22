"""Add design-partner pilot and case-study measurement.

Revision ID: 0028_design_partners
Revises: 0027_benchmark_net
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_design_partners"
down_revision = "0027_benchmark_net"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "design_partner_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="prospect"),
        sa.Column("champion_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("champion_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("pain_profile", sa.Text(), nullable=False, server_default=""),
        sa.Column("success_targets_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("target_case_study_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", name="uq_design_partner_org"),
        sa.CheckConstraint("status in ('prospect','pilot','live','case_study','graduated','churned')", name="ck_design_partner_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_design_partner_accounts_organization_id", "design_partner_accounts", ["organization_id"])
    op.create_index("ix_design_partner_status", "design_partner_accounts", ["status","started_at"])

    op.create_table(
        "design_partner_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("current_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(64), nullable=False, server_default=""),
        sa.Column("direction", sa.String(16), nullable=False, server_default="higher"),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("account_id","metric_key", name="uq_design_partner_metric_key"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["design_partner_accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_design_partner_metrics_organization_id", "design_partner_metrics", ["organization_id"])
    op.create_index("ix_design_partner_metrics_account_id", "design_partner_metrics", ["account_id"])

    op.create_table(
        "design_partner_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("area", sa.String(120), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False, server_default="medium"),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("submitted_by", sa.String(255), nullable=False),
        sa.Column("resolved_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("severity in ('low','medium','high','critical')", name="ck_design_partner_feedback_severity"),
        sa.CheckConstraint("status in ('open','planned','shipped','declined')", name="ck_design_partner_feedback_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["design_partner_accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_design_partner_feedback_organization_id", "design_partner_feedback", ["organization_id"])
    op.create_index("ix_design_partner_feedback_account_id", "design_partner_feedback", ["account_id"])
    op.create_index("ix_design_partner_feedback_account_status", "design_partner_feedback", ["account_id","status","created_at"])

    if op.get_bind().dialect.name == "postgresql":
        for table in ("design_partner_accounts","design_partner_metrics","design_partner_feedback"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("design_partner_feedback")
    op.drop_table("design_partner_metrics")
    op.drop_table("design_partner_accounts")
