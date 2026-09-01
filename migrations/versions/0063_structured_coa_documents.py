"""Add structured COA document and analyte persistence.

Revision ID: 0063_structured_coa_documents
Revises: 0062_inventory_transfers
"""

import sqlalchemy as sa
from alembic import op

revision = "0063_structured_coa_documents"
down_revision = "0062_inventory_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coa_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lot_id", sa.String(36), sa.ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("package_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("source", sa.String(64), nullable=False, server_default="library_upload"),
        sa.Column("status", sa.String(32), nullable=False, server_default="parsed"),
        sa.Column("verification_state", sa.String(32), nullable=False, server_default="unverified"),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False, server_default="application/pdf"),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("payload_compressed", sa.LargeBinary(), nullable=False),
        sa.Column("payload_size", sa.Integer(), nullable=False),
        sa.Column("parser_name", sa.String(96), nullable=False, server_default="doobielogic-coa"),
        sa.Column("parser_version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("product_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("product_type", sa.String(255), nullable=False, server_default=""),
        sa.Column("strain_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("batch_number", sa.String(255), nullable=False, server_default=""),
        sa.Column("lab_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("lab_license_number", sa.String(255), nullable=False, server_default=""),
        sa.Column("lab_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("metrc_source_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("metrc_lab_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("metrc_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("date_tested", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_collected", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_received", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overall_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("total_thc_percent", sa.Float(), nullable=True),
        sa.Column("total_cbd_percent", sa.Float(), nullable=True),
        sa.Column("total_cannabinoids_percent", sa.Float(), nullable=True),
        sa.Column("total_terpenes_percent", sa.Float(), nullable=True),
        sa.Column("raw_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("imported_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "facility_id", "fingerprint", name="uq_coa_document_scope_fingerprint"),
    )
    op.create_index("ix_coa_documents_organization_id", "coa_documents", ["organization_id"])
    op.create_index("ix_coa_documents_facility_id", "coa_documents", ["facility_id"])
    op.create_index("ix_coa_documents_lot_id", "coa_documents", ["lot_id"])
    op.create_index("ix_coa_documents_package_id", "coa_documents", ["package_id"])
    op.create_index("ix_coa_documents_metrc_source_id", "coa_documents", ["metrc_source_id"])
    op.create_index("ix_coa_document_scope_package", "coa_documents", ["organization_id", "facility_id", "package_id", "status"])
    op.create_index("ix_coa_document_scope_metrc_source", "coa_documents", ["organization_id", "facility_id", "metrc_source_id"])
    op.create_index("ix_coa_document_lot", "coa_documents", ["lot_id", "status"])

    op.create_table(
        "coa_analyte_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("coa_document_id", sa.String(36), sa.ForeignKey("coa_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("analysis", sa.String(96), nullable=False, server_default=""),
        sa.Column("analyte_key", sa.String(160), nullable=False, server_default=""),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("value_text", sa.String(64), nullable=False, server_default=""),
        sa.Column("units", sa.String(64), nullable=False, server_default=""),
        sa.Column("mg_g", sa.Float(), nullable=True),
        sa.Column("limit_value", sa.Float(), nullable=True),
        sa.Column("lod", sa.Float(), nullable=True),
        sa.Column("loq", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_coa_analyte_results_coa_document_id", "coa_analyte_results", ["coa_document_id"])
    op.create_index("ix_coa_analyte_results_organization_id", "coa_analyte_results", ["organization_id"])
    op.create_index("ix_coa_analyte_results_facility_id", "coa_analyte_results", ["facility_id"])
    op.create_index("ix_coa_analyte_document_order", "coa_analyte_results", ["coa_document_id", "sort_order"])
    op.create_index("ix_coa_analyte_scope_key", "coa_analyte_results", ["organization_id", "facility_id", "analyte_key"])

    with op.batch_alter_table("lot_quality_evidence") as batch:
        batch.add_column(sa.Column("coa_document_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("total_thc_percent", sa.Float(), nullable=True))
        batch.add_column(sa.Column("total_cbd_percent", sa.Float(), nullable=True))
        batch.add_column(sa.Column("total_cannabinoids_percent", sa.Float(), nullable=True))
        batch.create_foreign_key("fk_lot_quality_coa_document", "coa_documents", ["coa_document_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_lot_quality_evidence_coa_document_id", ["coa_document_id"])


def downgrade() -> None:
    with op.batch_alter_table("lot_quality_evidence") as batch:
        batch.drop_index("ix_lot_quality_evidence_coa_document_id")
        batch.drop_constraint("fk_lot_quality_coa_document", type_="foreignkey")
        batch.drop_column("total_cannabinoids_percent")
        batch.drop_column("total_cbd_percent")
        batch.drop_column("total_thc_percent")
        batch.drop_column("coa_document_id")

    op.drop_index("ix_coa_analyte_scope_key", table_name="coa_analyte_results")
    op.drop_index("ix_coa_analyte_document_order", table_name="coa_analyte_results")
    op.drop_index("ix_coa_analyte_results_facility_id", table_name="coa_analyte_results")
    op.drop_index("ix_coa_analyte_results_organization_id", table_name="coa_analyte_results")
    op.drop_index("ix_coa_analyte_results_coa_document_id", table_name="coa_analyte_results")
    op.drop_table("coa_analyte_results")

    op.drop_index("ix_coa_document_lot", table_name="coa_documents")
    op.drop_index("ix_coa_document_scope_metrc_source", table_name="coa_documents")
    op.drop_index("ix_coa_document_scope_package", table_name="coa_documents")
    op.drop_index("ix_coa_documents_metrc_source_id", table_name="coa_documents")
    op.drop_index("ix_coa_documents_package_id", table_name="coa_documents")
    op.drop_index("ix_coa_documents_lot_id", table_name="coa_documents")
    op.drop_index("ix_coa_documents_facility_id", table_name="coa_documents")
    op.drop_index("ix_coa_documents_organization_id", table_name="coa_documents")
    op.drop_table("coa_documents")
