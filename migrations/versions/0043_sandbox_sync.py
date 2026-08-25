"""Add durable sandbox integration sync staging and cursor state.

Revision ID: 0043_sandbox_sync
Revises: 0042_sandbox_providers
"""

from alembic import op
import sqlalchemy as sa

revision = "0043_sandbox_sync"
down_revision = "0042_sandbox_providers"
branch_labels = None
depends_on = None

_PROVIDER_CHECK = "provider in ('metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')"


def upgrade() -> None:
    op.create_table(
        "integration_sync_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(length=36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=24), nullable=False, server_default="sandbox"),
        sa.Column("cursor", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="idle"),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "facility_id", "provider", "resource", name="uq_integration_sync_state_scope"),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_integration_sync_state_provider"),
        sa.CheckConstraint("status in ('idle','running','succeeded','failed')", name="ck_integration_sync_state_status"),
    )
    op.create_index("ix_integration_sync_state_facility", "integration_sync_states", ["facility_id", "provider", "status"])
    op.create_index("ix_integration_sync_states_organization_id", "integration_sync_states", ["organization_id"])
    op.create_index("ix_integration_sync_states_facility_id", "integration_sync_states", ["facility_id"])

    op.create_table(
        "integration_sync_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(length=36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("raw_payload_json", sa.Text(), nullable=False),
        sa.Column("normalized_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="accepted"),
        sa.Column("error_message", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "facility_id", "provider", "resource", "fingerprint", name="uq_integration_sync_record_fingerprint"),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_integration_sync_record_provider"),
        sa.CheckConstraint("status in ('accepted','error')", name="ck_integration_sync_record_status"),
    )
    op.create_index("ix_integration_sync_record_external", "integration_sync_records", ["facility_id", "provider", "resource", "external_id"])
    op.create_index("ix_integration_sync_record_received", "integration_sync_records", ["facility_id", "received_at"])
    op.create_index("ix_integration_sync_records_organization_id", "integration_sync_records", ["organization_id"])
    op.create_index("ix_integration_sync_records_facility_id", "integration_sync_records", ["facility_id"])
    op.create_index("ix_integration_sync_records_run_id", "integration_sync_records", ["run_id"])
    op.create_index("ix_integration_sync_records_external_id", "integration_sync_records", ["external_id"])

    op.create_table(
        "integration_sync_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(length=36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("cursor_before", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("cursor_after", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_integration_sync_attempt_provider"),
        sa.CheckConstraint("status in ('running','succeeded','failed')", name="ck_integration_sync_attempt_status"),
    )
    op.create_index("ix_integration_sync_attempt_facility", "integration_sync_attempts", ["facility_id", "provider", "started_at"])
    op.create_index("ix_integration_sync_attempts_organization_id", "integration_sync_attempts", ["organization_id"])
    op.create_index("ix_integration_sync_attempts_facility_id", "integration_sync_attempts", ["facility_id"])
    op.create_index("ix_integration_sync_attempts_run_id", "integration_sync_attempts", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_integration_sync_attempts_run_id", table_name="integration_sync_attempts")
    op.drop_index("ix_integration_sync_attempts_facility_id", table_name="integration_sync_attempts")
    op.drop_index("ix_integration_sync_attempts_organization_id", table_name="integration_sync_attempts")
    op.drop_index("ix_integration_sync_attempt_facility", table_name="integration_sync_attempts")
    op.drop_table("integration_sync_attempts")
    op.drop_index("ix_integration_sync_records_external_id", table_name="integration_sync_records")
    op.drop_index("ix_integration_sync_records_run_id", table_name="integration_sync_records")
    op.drop_index("ix_integration_sync_records_facility_id", table_name="integration_sync_records")
    op.drop_index("ix_integration_sync_records_organization_id", table_name="integration_sync_records")
    op.drop_index("ix_integration_sync_record_received", table_name="integration_sync_records")
    op.drop_index("ix_integration_sync_record_external", table_name="integration_sync_records")
    op.drop_table("integration_sync_records")
    op.drop_index("ix_integration_sync_states_facility_id", table_name="integration_sync_states")
    op.drop_index("ix_integration_sync_states_organization_id", table_name="integration_sync_states")
    op.drop_index("ix_integration_sync_state_facility", table_name="integration_sync_states")
    op.drop_table("integration_sync_states")
