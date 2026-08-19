begin;

create table if not exists public.package_studio_runs (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_number varchar(64) not null,
    action_type varchar(32) not null,
    status varchar(24) not null default 'draft',
    source_quantity double precision not null default 0,
    source_unit varchar(32) not null default '',
    loss_quantity double precision not null default 0,
    reason varchar(255) not null default '',
    notes text not null default '',
    production_order_id varchar(36) references public.coman_production_orders(id) on delete set null,
    commercial_order_id varchar(36),
    external_sync_status varchar(24) not null default 'not_requested',
    external_sync_reference varchar(255) not null default '',
    created_by varchar(255) not null,
    completed_by varchar(255) not null default '',
    committed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_package_studio_org_run_number unique (organization_id, run_number),
    constraint ck_package_studio_action_type check (
        action_type in ('breakdown','pack_down','build_run','multi_build','sample_pull','rework','correction')
    ),
    constraint ck_package_studio_status check (status in ('draft','reserved','committed','cancelled')),
    constraint ck_package_studio_source_qty check (source_quantity >= 0),
    constraint ck_package_studio_loss_qty check (loss_quantity >= 0),
    constraint ck_package_studio_sync_status check (
        external_sync_status in ('not_requested','pending','synced','failed')
    )
);

create index if not exists ix_package_studio_runs_organization_id on public.package_studio_runs(organization_id);
create index if not exists ix_package_studio_runs_facility_id on public.package_studio_runs(facility_id);
create index if not exists ix_package_studio_facility_status on public.package_studio_runs(facility_id, status, created_at);

create table if not exists public.package_studio_inputs (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.package_studio_runs(id) on delete cascade,
    lot_id varchar(36) not null references public.coman_inventory_lots(id) on delete restrict,
    position integer not null,
    quantity double precision not null,
    unit varchar(32) not null,
    purpose varchar(64) not null default 'source',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_package_studio_input_position unique (run_id, position),
    constraint ck_package_studio_input_qty check (quantity > 0)
);

create index if not exists ix_package_studio_inputs_organization_id on public.package_studio_inputs(organization_id);
create index if not exists ix_package_studio_inputs_facility_id on public.package_studio_inputs(facility_id);
create index if not exists ix_package_studio_inputs_run_id on public.package_studio_inputs(run_id);
create index if not exists ix_package_studio_input_lot on public.package_studio_inputs(lot_id, run_id);

create table if not exists public.package_studio_outputs (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.package_studio_runs(id) on delete cascade,
    product_id varchar(36) not null references public.coman_products(id) on delete restrict,
    lot_id varchar(36) references public.coman_inventory_lots(id) on delete set null,
    position integer not null,
    lot_code varchar(255) not null,
    compliance_package_id varchar(255) not null default '',
    inventory_quantity double precision not null,
    inventory_unit varchar(32) not null,
    source_equivalent_quantity double precision not null default 0,
    source_equivalent_unit varchar(32) not null default '',
    purpose varchar(32) not null default 'standard',
    location_code varchar(120) not null default 'FINISHED-GOODS',
    notes text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_package_studio_output_position unique (run_id, position),
    constraint uq_package_studio_output_lot_code unique (facility_id, lot_code),
    constraint ck_package_studio_output_inventory_qty check (inventory_quantity > 0),
    constraint ck_package_studio_output_source_eq_qty check (source_equivalent_quantity >= 0),
    constraint ck_package_studio_output_purpose check (
        purpose in ('standard','lab_sample','trade_sample','retail_sample','rework','corrected')
    )
);

create index if not exists ix_package_studio_outputs_organization_id on public.package_studio_outputs(organization_id);
create index if not exists ix_package_studio_outputs_facility_id on public.package_studio_outputs(facility_id);
create index if not exists ix_package_studio_outputs_run_id on public.package_studio_outputs(run_id);
create index if not exists ix_package_studio_outputs_product_id on public.package_studio_outputs(product_id);
create index if not exists ix_package_studio_output_lot on public.package_studio_outputs(lot_id, run_id);

alter table public.package_studio_runs enable row level security;
alter table public.package_studio_inputs enable row level security;
alter table public.package_studio_outputs enable row level security;

comment on table public.package_studio_runs is
    'Tenant-scoped Buyer Dash Package Studio transformation events; inventory balances remain ledger-derived.';

update public.alembic_version
set version_num = '0017_package_studio'
where version_num = '0016_durable_data_hub_imports';

commit;
