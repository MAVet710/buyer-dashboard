"""Add organization-scoped Dutchie catalog nomenclature mappings.

Revision ID: 0010_catalog_nomenclature_mapper
Revises: 0009_repair_vapejet_library
"""

from alembic import op

from modules.coman.models import CatalogNomenclatureItem, CatalogNomenclatureMapping

revision = "0010_catalog_nomenclature_mapper"
down_revision = "0009_repair_vapejet_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    CatalogNomenclatureItem.__table__.create(bind=bind, checkfirst=True)
    CatalogNomenclatureMapping.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table catalog_nomenclature_items enable row level security")
        op.execute("alter table catalog_nomenclature_mappings enable row level security")


def downgrade() -> None:
    op.drop_table("catalog_nomenclature_mappings")
    op.drop_table("catalog_nomenclature_items")
