"""Allow non-cannabis ingredients in the canonical product master.

Revision ID: 0075_product_ingredients
Revises: 0074_supplier_portal_offers
"""

from alembic import op

revision = "0075_product_ingredients"
down_revision = "0074_supplier_portal_offers"
branch_labels = None
depends_on = None

NEW_CHECK = "item_type in ('cannabis', 'ingredient', 'packaging', 'wip', 'finished_good')"
OLD_CHECK = "item_type in ('cannabis', 'packaging', 'wip', 'finished_good')"


def _replace_product_type_check(expression: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE coman_products DROP CONSTRAINT IF EXISTS ck_coman_product_type")
        op.create_check_constraint("ck_coman_product_type", "coman_products", expression)
        return

    with op.batch_alter_table("coman_products", recreate="always") as batch:
        batch.drop_constraint("ck_coman_product_type", type_="check")
        batch.create_check_constraint("ck_coman_product_type", expression)


def upgrade() -> None:
    _replace_product_type_check(NEW_CHECK)


def downgrade() -> None:
    # Downgrade intentionally fails rather than deleting data when ingredient
    # products still exist. Operators must reclassify those products explicitly
    # before returning to a schema that cannot represent them.
    _replace_product_type_check(OLD_CHECK)
