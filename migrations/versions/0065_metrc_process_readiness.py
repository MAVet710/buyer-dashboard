"""Add Metrc process-readiness state.

Revision ID: 0065_metrc_process_readiness
Revises: 0064_packaging_label_semantics
"""

import sqlalchemy as sa
from alembic import op

revision = "0065_metrc_process_readiness"
down_revision = "0064_packaging_label_semantics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regulatory_metrc_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jurisdiction_code", sa.String(16), nullable=False),
        sa.Column("license_number", sa.String(160), nullable=False),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column("tag_type", sa.String(16), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="available"),
        sa.Column("reserved_for_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("reserved_for_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("facility_id", "environment", "tag_type", "label", name="uq_metrc_tag_facility_environment_type_label"),
        sa.CheckConstraint("tag_type in ('plant','package')", name="ck_metrc_tag_type"),
        sa.CheckConstraint("status in ('available','unavailable','reserved','used','voided')", name="ck_metrc_tag_status"),
    )
    op.create_index("ix_metrc_tag_available", "regulatory_metrc_tags", ["facility_id", "environment", "tag_type", "status"])
    op.create_index("ix_regulatory_metrc_tags_organization_id", "regulatory_metrc_tags", ["organization_id"])
    op.create_index("ix_regulatory_metrc_tags_facility_id", "regulatory_metrc_tags", ["facility_id"])

    op.create_table(
        "cultivation_regulatory_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin_type", sa.String(32), nullable=False),
        sa.Column("origin_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("metrc_plant_tag", sa.String(64), nullable=True),
        sa.Column("previous_metrc_plant_tag", sa.String(64), nullable=False, server_default=""),
        sa.Column("tag_assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tag_replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("plant_id", name="uq_cultivation_regulatory_identity_plant"),
        sa.UniqueConstraint("facility_id", "metrc_plant_tag", name="uq_cultivation_regulatory_metrc_tag"),
        sa.CheckConstraint("origin_type in ('mother','source_package','transfer','beginning_inventory','state_authorized','legacy_demo')", name="ck_cultivation_regulatory_origin_type"),
    )
    op.create_index("ix_cultivation_regulatory_identity_facility", "cultivation_regulatory_identities", ["facility_id", "metrc_plant_tag"])
    op.create_index("ix_cultivation_regulatory_identities_organization_id", "cultivation_regulatory_identities", ["organization_id"])
    op.create_index("ix_cultivation_regulatory_identities_plant_id", "cultivation_regulatory_identities", ["plant_id"])

    op.create_table(
        "cultivation_harvest_plant_weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("harvest_id", sa.String(36), sa.ForeignKey("cultivation_harvests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("wet_weight_g", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.UniqueConstraint("harvest_id", "plant_id", name="uq_cultivation_harvest_plant_weight"),
        sa.CheckConstraint("wet_weight_g >= 0", name="ck_cultivation_harvest_plant_wet_weight"),
    )
    op.create_index("ix_cultivation_harvest_plant_weight_harvest", "cultivation_harvest_plant_weights", ["harvest_id"])
    op.create_index("ix_cultivation_harvest_plant_weights_organization_id", "cultivation_harvest_plant_weights", ["organization_id"])
    op.create_index("ix_cultivation_harvest_plant_weights_facility_id", "cultivation_harvest_plant_weights", ["facility_id"])
    op.create_index("ix_cultivation_harvest_plant_weights_plant_id", "cultivation_harvest_plant_weights", ["plant_id"])

    op.create_table(
        "cultivation_waste_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(24), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("method", sa.String(255), nullable=False),
        sa.Column("material_mixed", sa.String(255), nullable=False, server_default=""),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("waste_date", sa.Date(), nullable=False),
        sa.Column("location", sa.String(160), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("target_type in ('plant','plant_group','harvest')", name="ck_cultivation_waste_target_type"),
        sa.CheckConstraint("weight >= 0", name="ck_cultivation_waste_weight"),
    )
    op.create_index("ix_cultivation_waste_target", "cultivation_waste_records", ["facility_id", "target_type", "target_id"])
    op.create_index("ix_cultivation_waste_records_organization_id", "cultivation_waste_records", ["organization_id"])

    op.create_table(
        "cultivation_manicure_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_code", sa.String(120), nullable=False),
        sa.Column("source_phase", sa.String(24), nullable=False),
        sa.Column("location", sa.String(160), nullable=False),
        sa.Column("manicure_date", sa.Date(), nullable=False),
        sa.Column("total_weight_g", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("facility_id", "batch_code", name="uq_cultivation_manicure_batch_code"),
        sa.CheckConstraint("source_phase in ('vegetative','flowering')", name="ck_cultivation_manicure_phase"),
        sa.CheckConstraint("total_weight_g >= 0", name="ck_cultivation_manicure_total_weight"),
    )
    op.create_index("ix_cultivation_manicure_batches_organization_id", "cultivation_manicure_batches", ["organization_id"])
    op.create_index("ix_cultivation_manicure_batches_facility_id", "cultivation_manicure_batches", ["facility_id"])

    op.create_table(
        "cultivation_manicure_plant_weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manicure_batch_id", sa.String(36), sa.ForeignKey("cultivation_manicure_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plant_id", sa.String(36), sa.ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("weight_g", sa.Float(), nullable=False),
        sa.UniqueConstraint("manicure_batch_id", "plant_id", name="uq_cultivation_manicure_plant"),
        sa.CheckConstraint("weight_g >= 0", name="ck_cultivation_manicure_plant_weight"),
    )
    op.create_index("ix_cultivation_manicure_plant_weights_organization_id", "cultivation_manicure_plant_weights", ["organization_id"])
    op.create_index("ix_cultivation_manicure_plant_weights_facility_id", "cultivation_manicure_plant_weights", ["facility_id"])
    op.create_index("ix_cultivation_manicure_plant_weights_manicure_batch_id", "cultivation_manicure_plant_weights", ["manicure_batch_id"])
    op.create_index("ix_cultivation_manicure_plant_weights_plant_id", "cultivation_manicure_plant_weights", ["plant_id"])

    op.create_table(
        "cultivation_additive_applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(24), nullable=False),
        sa.Column("target_id", sa.String(160), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("epa_number", sa.String(120), nullable=False, server_default=""),
        sa.Column("supplier", sa.String(255), nullable=False, server_default=""),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("active_ingredients", sa.Text(), nullable=False, server_default=""),
        sa.Column("application_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("target_type in ('plant','plant_group','location')", name="ck_cultivation_additive_target_type"),
        sa.CheckConstraint("amount >= 0", name="ck_cultivation_additive_amount"),
    )
    op.create_index("ix_cultivation_additive_target", "cultivation_additive_applications", ["facility_id", "target_type", "target_id"])
    op.create_index("ix_cultivation_additive_applications_organization_id", "cultivation_additive_applications", ["organization_id"])

    op.create_table(
        "cultivation_test_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("package_tag", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("provider_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("facility_id", "environment", "package_tag", name="uq_cultivation_test_sample_package_tag"),
        sa.CheckConstraint("environment in ('sandbox','production')", name="ck_cultivation_test_sample_environment"),
        sa.CheckConstraint("source_type in ('harvest','package')", name="ck_cultivation_test_sample_source_type"),
        sa.CheckConstraint("quantity > 0", name="ck_cultivation_test_sample_quantity"),
        sa.CheckConstraint("status in ('planned','provider_confirmed','verified','cancelled')", name="ck_cultivation_test_sample_status"),
    )
    op.create_index("ix_cultivation_test_sample_source", "cultivation_test_samples", ["facility_id", "source_type", "source_id"])
    op.create_index("ix_cultivation_test_samples_organization_id", "cultivation_test_samples", ["organization_id"])

    op.create_table(
        "metrc_transfer_controls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transfer_id", sa.String(36), sa.ForeignKey("inventory_transfers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_transfer_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_status", sa.String(32), nullable=False, server_default="prepared"),
        sa.Column("departure_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departure_confirmed_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("transfer_id", name="uq_metrc_transfer_control_transfer"),
        sa.CheckConstraint("provider_status in ('prepared','departed','partially_received','received','rejected','returned')", name="ck_metrc_transfer_control_status"),
    )
    op.create_index("ix_metrc_transfer_controls_organization_id", "metrc_transfer_controls", ["organization_id"])
    op.create_index("ix_metrc_transfer_controls_transfer_id", "metrc_transfer_controls", ["transfer_id"])

    op.create_table(
        "metrc_transfer_line_returns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transfer_id", sa.String(36), sa.ForeignKey("inventory_transfers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transfer_line_id", sa.String(36), sa.ForeignKey("inventory_transfer_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="rejected"),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rejected_by", sa.String(255), nullable=False),
        sa.Column("return_manifest_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("transfer_line_id", name="uq_metrc_transfer_line_return_line"),
        sa.CheckConstraint("status in ('rejected','returning','returned')", name="ck_metrc_transfer_line_return_status"),
    )
    op.create_index("ix_metrc_transfer_line_returns_organization_id", "metrc_transfer_line_returns", ["organization_id"])
    op.create_index("ix_metrc_transfer_line_returns_transfer_id", "metrc_transfer_line_returns", ["transfer_id"])
    op.create_index("ix_metrc_transfer_line_returns_transfer_line_id", "metrc_transfer_line_returns", ["transfer_line_id"])


def downgrade() -> None:
    for table in (
        "metrc_transfer_line_returns",
        "metrc_transfer_controls",
        "cultivation_test_samples",
        "cultivation_additive_applications",
        "cultivation_manicure_plant_weights",
        "cultivation_manicure_batches",
        "cultivation_waste_records",
        "cultivation_harvest_plant_weights",
        "cultivation_regulatory_identities",
        "regulatory_metrc_tags",
    ):
        op.drop_table(table)
