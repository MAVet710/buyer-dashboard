begin;

create table if not exists public.data_hub_imports (
    id varchar(36) primary key,
    organization_id varchar(36) not null
        references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null
        references public.coman_facilities(id) on delete cascade,
    dataset_key varchar(48) not null,
    dataset_label varchar(120) not null,
    cache_key varchar(64) not null,
    filename varchar(512) not null,
    content_type varchar(255) not null default '',
    fingerprint varchar(64) not null,
    payload_compressed bytea not null,
    payload_size integer not null,
    compressed_size integer not null,
    row_count integer not null default 0,
    column_count integer not null default 0,
    quality varchar(32) not null default '',
    mapping_json text not null default '{}',
    missing_fields_json text not null default '[]',
    status varchar(24) not null default 'active',
    imported_by_user_id varchar(36)
        references public.app_users(id) on delete set null,
    imported_by varchar(255) not null default 'system',
    activated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_data_hub_import_scope_fingerprint
        unique (organization_id, facility_id, dataset_key, fingerprint),
    constraint ck_data_hub_import_status
        check (status in ('active', 'archived')),
    constraint ck_data_hub_import_payload_size check (payload_size >= 0),
    constraint ck_data_hub_import_compressed_size check (compressed_size >= 0)
);

create index if not exists ix_data_hub_imports_organization_id
    on public.data_hub_imports(organization_id);
create index if not exists ix_data_hub_imports_facility_id
    on public.data_hub_imports(facility_id);
create index if not exists ix_data_hub_imports_imported_by_user_id
    on public.data_hub_imports(imported_by_user_id);
create index if not exists ix_data_hub_import_scope_status
    on public.data_hub_imports(
        organization_id, facility_id, dataset_key, status, created_at
    );
create unique index if not exists uq_data_hub_import_one_active
    on public.data_hub_imports(organization_id, facility_id, dataset_key)
    where status = 'active';

alter table public.data_hub_imports enable row level security;

comment on table public.data_hub_imports is
    'Compressed, versioned source files published through Data Hub and isolated by organization and facility.';

update public.alembic_version
set version_num = '0016_durable_data_hub_imports'
where version_num = '0015_inventory_audit_lifecycle';

commit;
