-- Extraction performance intelligence. Apply after 0021_extraction_erp.

create table if not exists public.extraction_resource_events (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.extraction_runs(id) on delete cascade,
    stage_key varchar(120) not null default '',
    resource_type varchar(24) not null,
    resource_name varchar(160) not null,
    quantity double precision not null,
    unit varchar(32) not null,
    recovered_quantity double precision,
    cost_usd double precision not null default 0,
    source_reference varchar(255) not null default '',
    notes text not null default '',
    actor varchar(255) not null,
    occurred_at timestamptz not null default now(),
    constraint ck_extraction_resource_type check (resource_type in ('solvent','utility','gas','consumable','water','other')),
    constraint ck_extraction_resource_quantity check (quantity >= 0),
    constraint ck_extraction_resource_recovered_nonnegative check (recovered_quantity is null or recovered_quantity >= 0),
    constraint ck_extraction_resource_recovered_le_quantity check (recovered_quantity is null or recovered_quantity <= quantity),
    constraint ck_extraction_resource_cost check (cost_usd >= 0)
);
create index if not exists ix_extraction_resource_events_organization_id on public.extraction_resource_events(organization_id);
create index if not exists ix_extraction_resource_events_facility_id on public.extraction_resource_events(facility_id);
create index if not exists ix_extraction_resource_events_run_id on public.extraction_resource_events(run_id);
create index if not exists ix_extraction_resource_run_time on public.extraction_resource_events(run_id, occurred_at);
create index if not exists ix_extraction_resource_facility_type on public.extraction_resource_events(facility_id, resource_type, occurred_at);

alter table public.extraction_resource_events enable row level security;

comment on table public.extraction_resource_events is 'Append-only extraction solvent, utility, gas, water and consumable usage/recovery events linked to durable runs.';

update public.alembic_version
set version_num = '0022_extraction_intel'
where version_num = '0021_extraction_erp';