begin;

create table if not exists public.product_master_profiles (
    product_id varchar(36) primary key references public.coman_products(id) on delete cascade,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    brand varchar(255) not null default '',
    category varchar(160) not null default '',
    subcategory varchar(160) not null default '',
    strain varchar(255) not null default '',
    manufacturer varchar(255) not null default '',
    product_format varchar(160) not null default '',
    description text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_product_master_profile_org_product unique (organization_id, product_id)
);
create index if not exists ix_product_master_profiles_organization_id on public.product_master_profiles(organization_id);
create index if not exists ix_product_master_profile_brand on public.product_master_profiles(organization_id, brand);
create index if not exists ix_product_master_profile_category on public.product_master_profiles(organization_id, category);

create table if not exists public.product_vendor_links (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    product_id varchar(36) not null references public.coman_products(id) on delete cascade,
    partner_id varchar(36) not null references public.commercial_trade_partners(id) on delete restrict,
    vendor_sku varchar(160) not null default '',
    is_primary boolean not null default false,
    lead_time_days integer not null default 0,
    minimum_order_quantity double precision not null default 0,
    case_pack double precision not null default 0,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_product_vendor_product_partner unique (product_id, partner_id),
    constraint ck_product_vendor_lead_time check (lead_time_days >= 0),
    constraint ck_product_vendor_moq check (minimum_order_quantity >= 0),
    constraint ck_product_vendor_case_pack check (case_pack >= 0)
);
create index if not exists ix_product_vendor_links_organization_id on public.product_vendor_links(organization_id);
create index if not exists ix_product_vendor_links_product_id on public.product_vendor_links(product_id);
create index if not exists ix_product_vendor_links_partner_id on public.product_vendor_links(partner_id);
create index if not exists ix_product_vendor_org_active on public.product_vendor_links(organization_id, active);

create table if not exists public.product_external_mappings (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    product_id varchar(36) not null references public.coman_products(id) on delete cascade,
    system_name varchar(64) not null,
    external_id varchar(255) not null,
    external_name varchar(512) not null default '',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_product_external_org_system_id unique (organization_id, system_name, external_id),
    constraint uq_product_external_product_system_id unique (product_id, system_name, external_id)
);
create index if not exists ix_product_external_mappings_organization_id on public.product_external_mappings(organization_id);
create index if not exists ix_product_external_mappings_product_id on public.product_external_mappings(product_id);
create index if not exists ix_product_external_lookup on public.product_external_mappings(organization_id, system_name, external_id);

create table if not exists public.product_aliases (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    product_id varchar(36) not null references public.coman_products(id) on delete cascade,
    alias varchar(512) not null,
    normalized_alias varchar(512) not null,
    source varchar(120) not null default 'manual',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_product_alias_org_normalized unique (organization_id, normalized_alias)
);
create index if not exists ix_product_aliases_organization_id on public.product_aliases(organization_id);
create index if not exists ix_product_aliases_product_id on public.product_aliases(product_id);
create index if not exists ix_product_alias_product on public.product_aliases(product_id, active);

create table if not exists public.product_value_events (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    product_id varchar(36) not null references public.coman_products(id) on delete cascade,
    partner_id varchar(36) references public.commercial_trade_partners(id) on delete set null,
    value_type varchar(32) not null,
    amount double precision not null,
    previous_amount double precision,
    currency varchar(8) not null default 'USD',
    source varchar(120) not null default 'manual',
    source_reference varchar(255) not null default '',
    actor varchar(255) not null,
    effective_at timestamptz not null default now(),
    constraint ck_product_value_type check (value_type in ('unit_cost','landed_cost','retail_price','wholesale_price')),
    constraint ck_product_value_amount check (amount >= 0)
);
create index if not exists ix_product_value_events_organization_id on public.product_value_events(organization_id);
create index if not exists ix_product_value_events_product_id on public.product_value_events(product_id);
create index if not exists ix_product_value_events_partner_id on public.product_value_events(partner_id);
create index if not exists ix_product_value_product_time on public.product_value_events(product_id, effective_at);
create index if not exists ix_product_value_org_type_time on public.product_value_events(organization_id, value_type, effective_at);

alter table public.product_master_profiles enable row level security;
alter table public.product_vendor_links enable row level security;
alter table public.product_external_mappings enable row level security;
alter table public.product_aliases enable row level security;
alter table public.product_value_events enable row level security;

update public.alembic_version
set version_num = '0020_product_master'
where version_num = '0019_pkgstudio_po_index';

commit;
