-- Permit deterministic DEV Sandbox teardown while keeping every real tenant's
-- inventory ledger immutable. Apply after 0028_design_partners.

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
$$;

update public.alembic_version
set version_num='0029_dev_sandbox_ledger_reset'
where version_num='0028_design_partners';
