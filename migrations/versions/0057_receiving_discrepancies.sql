create table if not exists public.traceability_receiving_discrepancies (
    id varchar(36) primary key,
    organization_id varchar not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar not null references public.coman_facilities(id) on delete restrict,
    preflight_id varchar(36) not null references public.traceability_receiving_preflights(id) on delete cascade,
    transfer_id varchar(255) not null,
    package_identity varchar(255) not null,
    provider_quantity varchar(64) not null default '0',
    observed_quantity varchar(64) not null default '0',
    unit varchar(64) not null default 'unit',
    discrepancy_type varchar(24) not null,
    status varchar(24) not null default 'open',
    note text not null default '',
    recorded_by varchar(255) not null,
    resolved_by varchar(255) not null default '',
    resolved_at timestamptz,
    resolution_note text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ck_receiving_discrepancy_status check (status in ('open','resolved','cancelled')),
    constraint ck_receiving_discrepancy_type check (discrepancy_type in ('short','over','missing','unexpected','damaged','other'))
);

create index if not exists ix_receiving_discrepancy_preflight_status
    on public.traceability_receiving_discrepancies(preflight_id, status, created_at);
create index if not exists ix_receiving_discrepancy_scope_transfer
    on public.traceability_receiving_discrepancies(organization_id, facility_id, transfer_id, created_at);
create index if not exists ix_traceability_receiving_discrepancies_organization_id
    on public.traceability_receiving_discrepancies(organization_id);
create index if not exists ix_traceability_receiving_discrepancies_facility_id
    on public.traceability_receiving_discrepancies(facility_id);
create index if not exists ix_traceability_receiving_discrepancies_preflight_id
    on public.traceability_receiving_discrepancies(preflight_id);

alter table public.traceability_receiving_discrepancies enable row level security;

update public.alembic_version
set version_num = '0057_receiving_discrepancies'
where version_num = '0056_trace_reconciliation';
