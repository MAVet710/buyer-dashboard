"""Add competitor cutover migration command center.

Revision ID: 0023_switch_center
Revises: 0022_extraction_intel
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_switch_center"
down_revision = "0022_extraction_intel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("source_system", sa.String(24), nullable=False),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False, server_default=""),
        sa.Column("fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="staged"),
        sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmapped_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("source_system in ('dutchie','distru','metrc','spreadsheet','other')", name="ck_migration_batch_source"),
        sa.CheckConstraint("entity_type in ('product','vendor','inventory','sales')", name="ck_migration_batch_entity"),
        sa.CheckConstraint("status in ('staged','review','ready','committed','cancelled','failed')", name="ck_migration_batch_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_migration_batches_organization_id", "migration_batches", ["organization_id"])
    op.create_index("ix_migration_batches_facility_id", "migration_batches", ["facility_id"])
    op.create_index("ix_migration_batch_facility_status", "migration_batches", ["facility_id", "status", "created_at"])

    op.create_table(
        "migration_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("source_external_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("normalized_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("match_status", sa.String(24), nullable=False, server_default="unmapped"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("canonical_entity_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("match_reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("decision_action", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("batch_id", "source_row_number", name="uq_migration_record_batch_row"),
        sa.CheckConstraint("match_status in ('auto_match','review_required','unmapped','conflict','committed','skipped')", name="ck_migration_record_match_status"),
        sa.CheckConstraint("decision_action in ('pending','accept','create','link','skip')", name="ck_migration_record_decision"),
        sa.CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_migration_record_confidence"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["migration_batches.id"], ondelete="CASCADE"),
    )
    for column in ("organization_id", "facility_id", "batch_id"):
        op.create_index(f"ix_migration_records_{column}", "migration_records", [column])
    op.create_index("ix_migration_record_batch_status", "migration_records", ["batch_id", "match_status", "source_row_number"])

    op.create_table(
        "migration_sales_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("source_system", sa.String(24), nullable=False),
        sa.Column("source_external_id", sa.String(255), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("units", sa.Float(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_record_id", sa.String(36), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "source_system", "source_external_id", name="uq_migration_sales_source"),
        sa.CheckConstraint("units >= 0", name="ck_migration_sales_units"),
        sa.CheckConstraint("revenue >= 0", name="ck_migration_sales_revenue"),
        sa.ForeignKeyConstraint(["organization_id"], ["coman_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["coman_facilities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["coman_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_record_id"], ["migration_records.id"], ondelete="SET NULL"),
    )
    for column in ("organization_id", "facility_id", "product_id", "source_record_id"):
        op.create_index(f"ix_migration_sales_history_{column}", "migration_sales_history", [column])
    op.create_index("ix_migration_sales_product_date", "migration_sales_history", ["product_id", "sale_date"])
    op.create_index("ix_migration_sales_facility_date", "migration_sales_history", ["facility_id", "sale_date"])

    if op.get_bind().dialect.name == "postgresql":
        for table in ("migration_batches", "migration_records", "migration_sales_history"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("migration_sales_history")
    op.drop_table("migration_records")
    op.drop_table("migration_batches")
