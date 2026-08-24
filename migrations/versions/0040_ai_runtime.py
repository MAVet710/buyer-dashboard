"""DoobieLogic native AI runtime persistence.

Revision ID: 0040_ai_runtime
Revises: 0039_extraction_step8
"""

from alembic import op
import sqlalchemy as sa

revision = "0040_ai_runtime"
down_revision = "0039_extraction_step8"
branch_labels = None
depends_on = None

TABLES = (
    "ai_knowledge_documents", "ai_knowledge_chunks", "ai_mapping_memory",
    "ai_telemetry", "ai_agent_feedback", "ai_agent_eval_cases",
)


def upgrade() -> None:
    op.create_table(
        "ai_knowledge_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source", sa.String(500), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(120), nullable=False),
        sa.Column("authority_level", sa.Integer(), nullable=False, server_default="99"),
        sa.Column("jurisdiction", sa.String(120), nullable=False, server_default=""),
        sa.Column("effective_date", sa.String(64), nullable=False, server_default=""),
        sa.Column("retrieved_or_uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(120), nullable=False, server_default=""),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_ai_knowledge_documents_scope", "ai_knowledge_documents", ["organization_id", "facility_id", "active"])
    op.create_index("ix_ai_knowledge_documents_hash", "ai_knowledge_documents", ["document_hash"])

    op.create_table(
        "ai_knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("ai_knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("chunk_number", sa.Integer(), nullable=False),
        sa.Column("page_or_section", sa.String(240), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("authority_level", sa.Integer(), nullable=False, server_default="99"),
        sa.Column("embedding_json", sa.Text(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("document_id", "chunk_number", name="uq_ai_knowledge_chunk_number"),
    )
    op.create_index("ix_ai_knowledge_chunks_scope", "ai_knowledge_chunks", ["organization_id", "facility_id", "authority_level"])
    op.create_index("ix_ai_knowledge_chunks_document", "ai_knowledge_chunks", ["document_id"])

    op.create_table(
        "ai_mapping_memory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dataset_type", sa.String(120), nullable=False),
        sa.Column("source_vendor", sa.String(160), nullable=False, server_default=""),
        sa.Column("normalized_source_header", sa.String(255), nullable=False),
        sa.Column("canonical_field", sa.String(160), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("origin", sa.String(80), nullable=False, server_default=""),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("human_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schema_fingerprint", sa.String(64), nullable=False),
    )
    op.create_index("ix_ai_mapping_memory_lookup", "ai_mapping_memory", ["organization_id", "facility_id", "dataset_type", "source_vendor", "schema_fingerprint"])

    op.create_table(
        "ai_telemetry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("task_category", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(160), nullable=False, server_default=""),
        sa.Column("is_local", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieval_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cloud_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("validation_result", sa.String(120), nullable=False, server_default=""),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_ai_telemetry_scope_time", "ai_telemetry", ["organization_id", "facility_id", "timestamp"])
    op.create_index("ix_ai_telemetry_provider", "ai_telemetry", ["provider", "model", "timestamp"])

    op.create_table(
        "ai_agent_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("normalized_task_type", sa.String(120), nullable=False),
        sa.Column("sanitized_prompt", sa.Text(), nullable=False),
        sa.Column("tool_names_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sanitized_tool_outcomes_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("user_rating", sa.Integer(), nullable=True),
        sa.Column("corrected_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("model", sa.String(160), nullable=False, server_default=""),
        sa.Column("evaluation_score", sa.Float(), nullable=True),
        sa.Column("training_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_ai_agent_feedback_scope", "ai_agent_feedback", ["organization_id", "facility_id", "agent", "created_at"])

    op.create_table(
        "ai_agent_eval_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_key", sa.String(160), nullable=False, unique=True),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("task_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("sanitized_prompt", sa.Text(), nullable=False),
        sa.Column("expected_assertions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(r"""
        DO $$
        DECLARE table_name text; role_name text;
        BEGIN
          FOREACH table_name IN ARRAY ARRAY['ai_knowledge_documents','ai_knowledge_chunks','ai_mapping_memory','ai_telemetry','ai_agent_feedback','ai_agent_eval_cases']
          LOOP
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
          END LOOP;
          FOREACH role_name IN ARRAY ARRAY['anon','authenticated']
          LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
              FOREACH table_name IN ARRAY ARRAY['ai_knowledge_documents','ai_knowledge_chunks','ai_mapping_memory','ai_telemetry','ai_agent_feedback','ai_agent_eval_cases']
              LOOP
                EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I', table_name, role_name);
              END LOOP;
            END IF;
          END LOOP;
        END $$;
        """)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
