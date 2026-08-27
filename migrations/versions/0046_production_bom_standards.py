"""Add version-bound production execution standards.

Revision ID: 0046_production_bom_standards
Revises: 0045_native_integrations
"""

from alembic import op
import sqlalchemy as sa

revision = "0046_production_bom_standards"
down_revision = "0045_native_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_bom_standards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bom_id", sa.String(36), sa.ForeignKey("coman_product_boms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("standard_labor_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("standard_machine_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("standard_cycle_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("resource_category", sa.String(120), nullable=False, server_default=""),
        sa.Column("qa_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("compliance_checkpoint", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bom_id", name="uq_production_bom_standard_bom"),
        sa.CheckConstraint("standard_labor_hours >= 0", name="ck_production_bom_standard_labor"),
        sa.CheckConstraint("standard_machine_hours >= 0", name="ck_production_bom_standard_machine"),
        sa.CheckConstraint("standard_cycle_hours >= 0", name="ck_production_bom_standard_cycle"),
    )
    op.create_index("ix_production_bom_standards_organization_id", "production_bom_standards", ["organization_id"])
    op.create_index("ix_production_bom_standards_bom_id", "production_bom_standards", ["bom_id"])
    op.create_index("ix_production_bom_standard_org_bom", "production_bom_standards", ["organization_id", "bom_id"])


def downgrade() -> None:
    op.drop_index("ix_production_bom_standard_org_bom", table_name="production_bom_standards")
    op.drop_index("ix_production_bom_standards_bom_id", table_name="production_bom_standards")
    op.drop_index("ix_production_bom_standards_organization_id", table_name="production_bom_standards")
    op.drop_table("production_bom_standards")
