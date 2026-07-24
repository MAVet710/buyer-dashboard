create table if not exists public.catalog_nomenclature_items (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    source_system varchar(32) not null default 'dutchie',
    canonical_name varchar(512) not null,
    normalized_name varchar(512) not null,
    sku varchar(255) not null default '',
    category varchar(255) not null default '',
    brand varchar(255) not null default '',
    active boolean not null default true,
    imported_by varchar(255) not null default 'system',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_catalog_nomenclature_org_source_name
        unique (organization_id, source_system, normalized_name)
);
create index if not exists ix_catalog_nomenclature_items_organization_id
    on public.catalog_nomenclature_items(organization_id);
create index if not exists ix_catalog_nomenclature_org_active
    on public.catalog_nomenclature_items(organization_id, active);

create table if not exists public.catalog_nomenclature_mappings (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    catalog_item_id varchar(36) references public.catalog_nomenclature_items(id) on delete set null,
    source_system varchar(32) not null default 'metrc',
    source_item_name varchar(512) not null,
    source_normalized_name varchar(512) not null,
    correct_name varchar(512) not null,
    status varchar(24) not null default 'confirmed',
    confirmed_by varchar(255) not null,
    confirmed_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_catalog_mapping_org_source_name
        unique (organization_id, source_system, source_normalized_name),
    constraint ck_catalog_mapping_status check (status in ('confirmed', 'retired'))
);
create index if not exists ix_catalog_nomenclature_mappings_organization_id
    on public.catalog_nomenclature_mappings(organization_id);
create index if not exists ix_catalog_nomenclature_mappings_catalog_item_id
    on public.catalog_nomenclature_mappings(catalog_item_id);
create index if not exists ix_catalog_mapping_org_status
    on public.catalog_nomenclature_mappings(organization_id, status);

alter table public.catalog_nomenclature_items enable row level security;
alter table public.catalog_nomenclature_mappings enable row level security;
