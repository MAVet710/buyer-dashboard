"""Allow canonical DEV Sandbox rebuilds to delete synthetic ledger rows.

Revision ID: 0029_dev_sandbox_ledger_reset
Revises: 0028_design_partners

The production inventory ledger remains append-only for every real organization.
Only DELETE operations whose existing row belongs to the canonical
``dev-sandbox`` organization are permitted so the deterministic developer
sandbox can be torn down and reseeded. UPDATE remains forbidden everywhere.
"""
from alembic import op

revision = "0029_dev_sandbox_ledger_reset"
down_revision = "0028_design_partners"
branch_labels = None
depends_on = None


STRICT_FUNCTION = """
create or replace function public.coman_prevent_inventory_ledger_mutation()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    raise exception 'Inventory ledger entries are immutable; post a correcting transaction instead.';
end;
$$
"""


SANDBOX_AWARE_FUNCTION = """
create or replace function public.coman_prevent_inventory_ledger_mutation()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    if TG_OP = 'DELETE' and exists (
        select 1
        from public.coman_organizations organization
        where organization.id = OLD.organization_id
          and organization.slug = 'dev-sandbox'
    ) then
        return OLD;
    end if;

    raise exception 'Inventory ledger entries are immutable; post a correcting transaction instead.';
end;
$$
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(SANDBOX_AWARE_FUNCTION)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(STRICT_FUNCTION)
