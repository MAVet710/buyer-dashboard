"""Add production integration providers, signed-webhook material, label printing, and accounting links.

Revision ID: 0045_native_integrations
Revises: 0044_operational_moats
"""

from alembic import op
import sqlalchemy as sa

revision = "0045_native_integrations"
down_revision = "0044_operational_moats"
branch_labels = None
depends_on = None


CONFIG_PROVIDERS = "'metrc','biotrack','quickbooks','doobie','ai_runtime','spacemail','metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox'"
SYNC_PROVIDERS = "'metrc','biotrack','quickbooks','metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox'"


def _replace_provider_check(table: str, constraint: str, values: str) -> None:
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(constraint, type_="check")
        batch.create_check_constraint(constraint, f"provider in ({values})")


def upgrade() -> None:
    _replace_provider_check("integration_configurations", "ck_integration_provider", CONFIG_PROVIDERS)
    _replace_provider_check("integration_sync_states", "ck_integration_sync_state_provider", SYNC_PROVIDERS)
    _replace_provider_check("integration_sync_records", "ck_integration_sync_record_provider", SYNC_PROVIDERS)
    _replace_provider_check("integration_sync_attempts", "ck_integration_sync_attempt_provider", SYNC_PROVIDERS)

    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.add_column(sa.Column("encrypted_secret", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("secret_hint", sa.String(32), nullable=False, server_default=""))

    op.create_table(
        "accounting_sync_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="quickbooks"),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("internal_id", sa.String(36), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("sync_token", sa.String(255), nullable=False, server_default=""),
        sa.Column("payload_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="synced"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "organization_id", "facility_id", "entity_type", "internal_id", name="uq_accounting_sync_internal"),
        sa.CheckConstraint("provider in ('quickbooks')", name="ck_accounting_sync_provider"),
        sa.CheckConstraint("entity_type in ('customer','vendor','item','invoice','payment','purchase_order','bill')", name="ck_accounting_sync_entity_type"),
        sa.CheckConstraint("status in ('synced','failed','stale')", name="ck_accounting_sync_status"),
    )
    op.create_index("ix_accounting_sync_external", "accounting_sync_links", ["organization_id", "facility_id", "provider", "entity_type", "external_id"])

    op.create_table(
        "printer_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("transport", sa.String(24), nullable=False, server_default="browser"),
        sa.Column("printer_key", sa.String(255), nullable=False, server_default=""),
        sa.Column("dpi", sa.Integer(), nullable=False, server_default="203"),
        sa.Column("width_mm", sa.Float(), nullable=False, server_default="50"),
        sa.Column("height_mm", sa.Float(), nullable=False, server_default="25"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("facility_id", "name", name="uq_printer_profile_name"),
        sa.CheckConstraint("transport in ('browser','edge','zpl')", name="ck_printer_profile_transport"),
    )
    op.create_index("ix_printer_profile_facility_active", "printer_profiles", ["facility_id", "active"])

    op.create_table(
        "label_print_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("printer_profile_id", sa.String(36), sa.ForeignKey("printer_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("label_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("label_review_id", sa.String(36), sa.ForeignKey("label_reviews.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("package_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("copies", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("format", sa.String(24), nullable=False, server_default="browser"),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("render_data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("rendered_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("override_reason", sa.String(512), nullable=False, server_default=""),
        sa.Column("queued_by", sa.String(255), nullable=False),
        sa.Column("dispatched_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint("copies > 0 and copies <= 500", name="ck_label_print_job_copies"),
        sa.CheckConstraint("format in ('browser','zpl')", name="ck_label_print_job_format"),
        sa.CheckConstraint("status in ('queued','rendered','dispatched','printed','failed','cancelled')", name="ck_label_print_job_status"),
    )
    op.create_index("ix_label_print_job_facility_status", "label_print_jobs", ["facility_id", "status", "queued_at"])
    op.create_index("ix_label_print_job_review", "label_print_jobs", ["label_review_id", "queued_at"])


def downgrade() -> None:
    op.drop_table("label_print_jobs")
    op.drop_table("printer_profiles")
    op.drop_table("accounting_sync_links")
    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.drop_column("secret_hint")
        batch.drop_column("encrypted_secret")
    _replace_provider_check("integration_sync_attempts", "ck_integration_sync_attempt_provider", "'metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox'")
    _replace_provider_check("integration_sync_records", "ck_integration_sync_record_provider", "'metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox'")
    _replace_provider_check("integration_sync_states", "ck_integration_sync_state_provider", "'metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox'")
    _replace_provider_check("integration_configurations", "ck_integration_provider", "'metrc','doobie','ai_runtime','spacemail','metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox'")
