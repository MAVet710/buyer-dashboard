"""Add trusted regulatory facility, license, provider, and environment mappings.

Revision ID: 0050_regulatory_mappings
Revises: 0049_product_menu_images
"""

from alembic import op
import sqlalchemy as sa


revision = "0050_regulatory_mappings"
down_revision = "0049_product_menu_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regulatory_facility_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_configuration_id", sa.String(36), sa.ForeignKey("integration_configurations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("jurisdiction_code", sa.String(16), nullable=False),
        sa.Column("license_number", sa.String(160), nullable=False),
        sa.Column("provider_facility_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider in ('metrc','biotrack')", name="ck_regulatory_mapping_provider"),
        sa.CheckConstraint("environment in ('sandbox','production')", name="ck_regulatory_mapping_environment"),
        sa.UniqueConstraint(
            "organization_id", "facility_id", "provider", "license_number", "environment",
            name="uq_regulatory_mapping_scope_license_environment",
        ),
    )
    op.create_index("ix_regulatory_mapping_organization_id", "regulatory_facility_mappings", ["organization_id"])
    op.create_index("ix_regulatory_mapping_facility_id", "regulatory_facility_mappings", ["facility_id"])
    op.create_index("ix_regulatory_mapping_integration_configuration_id", "regulatory_facility_mappings", ["integration_configuration_id"])
    op.create_index("ix_regulatory_mapping_active", "regulatory_facility_mappings", ["organization_id", "facility_id", "provider", "active"])


def downgrade() -> None:
    op.drop_index("ix_regulatory_mapping_active", table_name="regulatory_facility_mappings")
    op.drop_index("ix_regulatory_mapping_integration_configuration_id", table_name="regulatory_facility_mappings")
    op.drop_index("ix_regulatory_mapping_facility_id", table_name="regulatory_facility_mappings")
    op.drop_index("ix_regulatory_mapping_organization_id", table_name="regulatory_facility_mappings")
    op.drop_table("regulatory_facility_mappings")
