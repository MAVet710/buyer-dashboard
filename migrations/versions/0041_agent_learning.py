"""Durable tenant-scoped agent learning signals.

Revision ID: 0041_agent_learning
Revises: 0040_ai_runtime
"""

from alembic import op
import sqlalchemy as sa

revision = "0041_agent_learning"
down_revision = "0040_ai_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_agent_feedback", sa.Column("learning_approved", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("ai_agent_feedback", sa.Column("learning_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_ai_agent_feedback_learning",
        "ai_agent_feedback",
        ["organization_id", "facility_id", "agent", "learning_approved", "created_at"],
    )

    op.create_table(
        "ai_agent_learnings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("learning_key", sa.String(255), nullable=False),
        sa.Column("learning_type", sa.String(80), nullable=False),
        sa.Column("source_kind", sa.String(80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "facility_id", "agent", "learning_key", name="uq_ai_agent_learning_scope_key"),
    )
    op.create_index(
        "ix_ai_agent_learnings_scope",
        "ai_agent_learnings",
        ["organization_id", "facility_id", "agent", "active", "last_observed_at"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.ai_agent_learnings ENABLE ROW LEVEL SECURITY")
        op.execute("""
        DO $$
        DECLARE role_name text;
        BEGIN
          FOREACH role_name IN ARRAY ARRAY['anon','authenticated']
          LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
              EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.ai_agent_learnings FROM %I', role_name);
            END IF;
          END LOOP;
        END $$;
        """)


def downgrade() -> None:
    op.drop_table("ai_agent_learnings")
    op.drop_index("ix_ai_agent_feedback_learning", table_name="ai_agent_feedback")
    op.drop_column("ai_agent_feedback", "learning_approved_at")
    op.drop_column("ai_agent_feedback", "learning_approved")
