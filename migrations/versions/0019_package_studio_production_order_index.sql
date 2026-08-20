begin;

create index if not exists ix_package_studio_runs_production_order_id
    on public.package_studio_runs(production_order_id);

update public.alembic_version
set version_num = '0019_pkgstudio_po_index'
where version_num = '0018_traceability_transactions';

commit;
