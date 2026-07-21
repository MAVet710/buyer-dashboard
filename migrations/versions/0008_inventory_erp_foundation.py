"""Add product BOMs, lots, immutable inventory ledger, and reservations."""
from alembic import op
from modules.coman.models import Product, ProductBom, BomComponent, InventoryLot, InventoryTransaction, MaterialReservation
revision = "0008_inventory_erp_foundation"
down_revision = "0007_machine_reference_library"
branch_labels = None
depends_on = None
def upgrade() -> None:
    bind = op.get_bind()
    for model in (Product, ProductBom, BomComponent, InventoryLot, InventoryTransaction, MaterialReservation):
        model.__table__.create(bind=bind, checkfirst=True)
        if bind.dialect.name == "postgresql":
            op.execute(f"alter table {model.__tablename__} enable row level security")
    if bind.dialect.name == "postgresql":
        op.execute("""
            create or replace function public.coman_prevent_inventory_ledger_mutation()
            returns trigger language plpgsql as $$
            begin
                raise exception 'Inventory ledger entries are immutable; post a correcting transaction instead.';
            end;
            $$
        """)
        op.execute("""
            create trigger coman_inventory_ledger_immutable
            before update or delete on public.coman_inventory_transactions
            for each row execute function public.coman_prevent_inventory_ledger_mutation()
        """)
def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("drop trigger if exists coman_inventory_ledger_immutable on public.coman_inventory_transactions")
        op.execute("drop function if exists public.coman_prevent_inventory_ledger_mutation()")
    for name in ("coman_material_reservations", "coman_inventory_transactions", "coman_inventory_lots", "coman_bom_components", "coman_product_boms", "coman_products"):
        op.drop_table(name)
