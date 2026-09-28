"""security guard active defense state

Revision ID: 0090_security_guard
Revises: 0089_connected_onboarding
"""
from alembic import op
import sqlalchemy as sa

revision="0090_security_guard"
down_revision="0089_connected_onboarding"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("security_guard_state",
        sa.Column("id",sa.String(80),primary_key=True), sa.Column("checked_at",sa.Float(),nullable=False),
        sa.Column("state",sa.String(24),nullable=False), sa.Column("threat_level",sa.String(16),nullable=False),
        sa.Column("risk_score",sa.Integer(),nullable=False), sa.Column("active_investigations",sa.Integer(),nullable=False),
        sa.Column("metrc_write_protection",sa.Boolean(),nullable=False), sa.Column("deception_armed",sa.Boolean(),nullable=False),
        sa.Column("ai_state",sa.String(24),nullable=False), sa.Column("ai_last_success",sa.Float(),nullable=False),
        sa.Column("detail_json",sa.Text(),nullable=False))
    op.create_table("security_investigations",
        sa.Column("id",sa.String(36),primary_key=True), sa.Column("fingerprint",sa.String(64),nullable=False,unique=True),
        sa.Column("opened_at",sa.Float(),nullable=False), sa.Column("updated_at",sa.Float(),nullable=False),
        sa.Column("status",sa.String(24),nullable=False), sa.Column("risk_score",sa.Integer(),nullable=False),
        sa.Column("confidence",sa.Float(),nullable=False), sa.Column("classification",sa.String(80),nullable=False),
        sa.Column("subject_key",sa.String(64),nullable=False), sa.Column("source_key",sa.String(64),nullable=False),
        sa.Column("evidence_json",sa.Text(),nullable=False), sa.Column("ai_summary",sa.Text(),nullable=False),
        sa.Column("recommended_state",sa.String(24),nullable=False), sa.Column("containment_json",sa.Text(),nullable=False),
        sa.Column("evidence_hash",sa.String(64),nullable=False))
    op.create_index("ix_security_investigation_status_risk","security_investigations",["status","risk_score","updated_at"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("security_guard_state","security_investigations"):
            op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'REVOKE ALL PRIVILEGES ON TABLE public."{table}" FROM anon, authenticated')

def downgrade():
    op.drop_index("ix_security_investigation_status_risk",table_name="security_investigations")
    op.drop_table("security_investigations"); op.drop_table("security_guard_state")
