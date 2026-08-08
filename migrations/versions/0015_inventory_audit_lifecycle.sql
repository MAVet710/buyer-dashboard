begin;

alter table public.inventory_audits
    drop constraint if exists ck_inventory_audit_status;

alter table public.inventory_audits
    add constraint ck_inventory_audit_status
    check (status in ('draft', 'in_progress', 'paused', 'stopped', 'completed', 'cancelled'));

update public.alembic_version
set version_num = '0015_inventory_audit_lifecycle'
where version_num = '0014_machine_reference_library';

commit;
