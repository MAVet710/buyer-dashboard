"""Add human-approved deterministic action layer.

Revision ID: 0026_doobie_actions
Revises: 0025_commercial_fin
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_doobie_actions"
down_revision = "0025_commercial_fin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("preview_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("financial_impact_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(24), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id","idempotency_key", name="uq_action_proposal_org_idempotency"),
        sa.CheckConstraint("risk_level in ('low','medium','high','compliance')", name="ck_action_proposal_risk"),
        sa.CheckConstraint("status in ('proposed','approved','executing','executed','rejected','failed','expired')", name="ck_action_proposal_status"),
        sa.CheckConstraint("financial_impact_usd >= 0", name="ck_action_proposal_financial_impact"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
    )
    for col in ("organization_id","facility_id"):
        op.create_index(f"ix_action_proposals_{col}", "action_proposals", [col])
    op.create_index("ix_action_proposal_facility_status", "action_proposals", ["facility_id","status","created_at"])

    op.create_table(
        "action_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="started"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("proposal_id","attempt_number", name="uq_action_execution_attempt"),
        sa.CheckConstraint("status in ('started','succeeded','failed')", name="ck_action_execution_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], ondelete="CASCADE"),
    )
    for col in ("organization_id","facility_id","proposal_id"):
        op.create_index(f"ix_action_executions_{col}", "action_executions", [col])
    op.create_index("ix_action_execution_proposal_time", "action_executions", ["proposal_id","started_at"])

    op.execute("ALTER TABLE action_proposals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE action_executions ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("action_executions")
    op.drop_table("action_proposals")
