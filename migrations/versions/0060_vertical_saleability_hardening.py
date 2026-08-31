"""Add canonical lot quality evidence and Product Master packaging semantics.

Revision ID: 0060_vertical_saleability
Revises: 0059_material_transformations
"""

import sqlalchemy as sa
from alembic import op

revision = "0060_vertical_saleability"
down_revision = "0059_material_transformations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lot_quality_evidence",
        sa.Column("lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lab_testing_state", sa.String(32), nullable=False, server_default=""),
        sa.Column("coa_reference", sa.String(512), nullable=False, server_default=""),
        sa.Column("coa_url", sa.String(1024), nullable=False, server_default=""),
        sa.Column("thca_percent", sa.Float(), nullable=True),
        sa.Column("tac_percent", sa.Float(), nullable=True),
        sa.Column("total_terpenes_percent", sa.Float(), nullable=True),
        sa.Column("evidence_source", sa.String(96), nullable=False, server_default="manual"),
        sa.Column("inherited_from_lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor", sa.String(255), nullable=False, server_default="system"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lot_quality_evidence_organization_id", "lot_quality_evidence", ["organization_id"])
    op.create_index("ix_lot_quality_evidence_facility_id", "lot_quality_evidence", ["facility_id"])
    op.create_index("ix_lot_quality_evidence_inherited_from_lot_id", "lot_quality_evidence", ["inherited_from_lot_id"])
    op.create_index("ix_lot_quality_scope_state", "lot_quality_evidence", ["organization_id", "facility_id", "lab_testing_state"])

    op.create_table(
        "product_packaging_profiles",
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("net_content", sa.Float(), nullable=False, server_default="0"),
        sa.Column("net_content_unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("units_per_package", sa.Float(), nullable=False, server_default="1"),
        sa.Column("sellable_unit", sa.String(32), nullable=False, server_default="each"),
        sa.Column("case_pack", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_packaging_profiles_organization_id", "product_packaging_profiles", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_product_packaging_profiles_organization_id", table_name="product_packaging_profiles")
    op.drop_table("product_packaging_profiles")
    op.drop_index("ix_lot_quality_scope_state", table_name="lot_quality_evidence")
    op.drop_index("ix_lot_quality_evidence_inherited_from_lot_id", table_name="lot_quality_evidence")
    op.drop_index("ix_lot_quality_evidence_facility_id", table_name="lot_quality_evidence")
    op.drop_index("ix_lot_quality_evidence_organization_id", table_name="lot_quality_evidence")
    op.drop_table("lot_quality_evidence")
