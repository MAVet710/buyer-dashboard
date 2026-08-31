"""Add canonical seed-to-sale material transformations.

Revision ID: 0059_material_transformations
Revises: 0058_offline_mutation_receipts
"""

import sqlalchemy as sa
from alembic import op

revision = "0059_material_transformations"
down_revision = "0058_offline_mutation_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_transformations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transformation_type", sa.String(64), nullable=False),
        sa.Column("source_entity_type", sa.String(64), nullable=False),
        sa.Column("source_entity_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "facility_id", "transformation_type", "source_entity_type", "source_entity_id",
            name="uq_material_transformation_source",
        ),
    )
    op.create_index("ix_material_transformations_organization_id", "material_transformations", ["organization_id"])
    op.create_index("ix_material_transformations_facility_id", "material_transformations", ["facility_id"])
    op.create_index("ix_material_transformations_source_entity_id", "material_transformations", ["source_entity_id"])
    op.create_index(
        "ix_material_transformation_scope_type", "material_transformations",
        ["organization_id", "facility_id", "transformation_type"],
    )

    op.create_table(
        "material_transformation_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transformation_id", sa.String(36), sa.ForeignKey("material_transformations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("purpose", sa.String(64), nullable=False, server_default="source"),
        sa.Column("measurement_basis", sa.String(24), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("transformation_id", "entity_type", "entity_id", "purpose", name="uq_material_transformation_input_entity"),
    )
    op.create_index("ix_material_transformation_inputs_organization_id", "material_transformation_inputs", ["organization_id"])
    op.create_index("ix_material_transformation_inputs_facility_id", "material_transformation_inputs", ["facility_id"])
    op.create_index("ix_material_transformation_inputs_transformation_id", "material_transformation_inputs", ["transformation_id"])
    op.create_index("ix_material_transformation_inputs_lot_id", "material_transformation_inputs", ["lot_id"])
    op.create_index("ix_material_transformation_inputs_product_id", "material_transformation_inputs", ["product_id"])
    op.create_index("ix_material_transformation_input_lot", "material_transformation_inputs", ["lot_id", "transformation_id"])
    op.create_index("ix_material_transformation_input_entity", "material_transformation_inputs", ["entity_type", "entity_id"])

    op.create_table(
        "material_transformation_outputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transformation_id", sa.String(36), sa.ForeignKey("material_transformations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False, server_default="standard"),
        sa.Column("measurement_basis", sa.String(24), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("transformation_id", "lot_id", name="uq_material_transformation_output_lot"),
    )
    op.create_index("ix_material_transformation_outputs_organization_id", "material_transformation_outputs", ["organization_id"])
    op.create_index("ix_material_transformation_outputs_facility_id", "material_transformation_outputs", ["facility_id"])
    op.create_index("ix_material_transformation_outputs_transformation_id", "material_transformation_outputs", ["transformation_id"])
    op.create_index("ix_material_transformation_outputs_lot_id", "material_transformation_outputs", ["lot_id"])
    op.create_index("ix_material_transformation_outputs_product_id", "material_transformation_outputs", ["product_id"])
    op.create_index("ix_material_transformation_output_lot", "material_transformation_outputs", ["lot_id", "transformation_id"])

    op.create_table(
        "material_transformation_losses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transformation_id", sa.String(36), sa.ForeignKey("material_transformations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("loss_type", sa.String(64), nullable=False, server_default="process_loss"),
        sa.Column("measurement_basis", sa.String(24), nullable=False, server_default=""),
        sa.Column("reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_material_transformation_losses_organization_id", "material_transformation_losses", ["organization_id"])
    op.create_index("ix_material_transformation_losses_facility_id", "material_transformation_losses", ["facility_id"])
    op.create_index("ix_material_transformation_losses_transformation_id", "material_transformation_losses", ["transformation_id"])
    op.create_index("ix_material_transformation_loss", "material_transformation_losses", ["transformation_id", "loss_type"])


def downgrade() -> None:
    op.drop_table("material_transformation_losses")
    op.drop_table("material_transformation_outputs")
    op.drop_table("material_transformation_inputs")
    op.drop_table("material_transformations")
