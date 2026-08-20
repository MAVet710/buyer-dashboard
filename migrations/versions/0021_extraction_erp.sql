-- Durable Extraction ERP foundation.
-- Apply only after 0020_product_master.

create table if not exists public.extraction_runs (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    production_order_id varchar(36) references public.coman_production_orders(id) on delete set null,
    customer_id varchar(36) references public.coman_customers(id) on delete set null,
    machine_id varchar(36) references public.coman_facility_machines(id) on delete set null,
    batch_number varchar(120) not null,
    method varchar(64) not null,
    workflow_key varchar(120) not null,
    current_stage_key varchar(120) not null default 'intake',
    status varchar(24) not null default 'planned',
    release_status varchar(24) not null default 'blocked',
    product_family varchar(160) not null default '',
    strain varchar(255) not null default '',
    toll_processing boolean not null default false,
    compliance_provider varchar(32) not null default 'metrc',
    license_number varchar(255) not null default '',
    operator varchar(255) not null default '',
    notes text not null default '',
    started_at timestamptz,
    completed_at timestamptz,
    created_by varchar(255) not null,
    updated_by varchar(255) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_extraction_run_org_batch unique (organization_id, batch_number),
    constraint ck_extraction_run_status check (status in ('planned','queued','active','hold','qa','complete','cancelled','failed')),
    constraint ck_extraction_release_status check (release_status in ('blocked','pending','approved','rejected'))
);
create index if not exists ix_extraction_runs_organization_id on public.extraction_runs(organization_id);
create index if not exists ix_extraction_runs_facility_id on public.extraction_runs(facility_id);
create index if not exists ix_extraction_runs_production_order_id on public.extraction_runs(production_order_id);
create index if not exists ix_extraction_runs_customer_id on public.extraction_runs(customer_id);
create index if not exists ix_extraction_runs_machine_id on public.extraction_runs(machine_id);
create index if not exists ix_extraction_runs_facility_status on public.extraction_runs(facility_id, status, created_at);
create index if not exists ix_extraction_runs_facility_stage on public.extraction_runs(facility_id, current_stage_key, updated_at);

create table if not exists public.extraction_run_inputs (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.extraction_runs(id) on delete cascade,
    lot_id varchar(36) not null references public.coman_inventory_lots(id) on delete restrict,
    role varchar(64) not null default 'primary_input',
    planned_quantity double precision not null default 0,
    reserved_quantity double precision not null default 0,
    consumed_quantity double precision not null default 0,
    unit varchar(32) not null,
    unit_cost_snapshot double precision not null default 0,
    input_cost_usd double precision not null default 0,
    source_reference varchar(255) not null default '',
    status varchar(24) not null default 'reserved',
    reserved_by varchar(255) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_extraction_input_run_lot_role unique (run_id, lot_id, role),
    constraint ck_extraction_input_planned check (planned_quantity >= 0),
    constraint ck_extraction_input_reserved check (reserved_quantity >= 0),
    constraint ck_extraction_input_consumed check (consumed_quantity >= 0),
    constraint ck_extraction_input_consume_le_reserve check (consumed_quantity <= reserved_quantity),
    constraint ck_extraction_input_status check (status in ('reserved','partial','consumed','released'))
);
create index if not exists ix_extraction_run_inputs_organization_id on public.extraction_run_inputs(organization_id);
create index if not exists ix_extraction_run_inputs_facility_id on public.extraction_run_inputs(facility_id);
create index if not exists ix_extraction_run_inputs_run_id on public.extraction_run_inputs(run_id);
create index if not exists ix_extraction_run_inputs_lot_id on public.extraction_run_inputs(lot_id);
create index if not exists ix_extraction_inputs_run_status on public.extraction_run_inputs(run_id, status);
create index if not exists ix_extraction_inputs_lot_status on public.extraction_run_inputs(lot_id, status);

create table if not exists public.extraction_stage_events (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.extraction_runs(id) on delete cascade,
    stage_key varchar(120) not null,
    event_type varchar(24) not null,
    input_weight_g double precision,
    output_weight_g double precision,
    loss_weight_g double precision,
    loss_reason varchar(255) not null default '',
    operator varchar(255) not null default '',
    machine_id varchar(36) references public.coman_facility_machines(id) on delete set null,
    notes text not null default '',
    occurred_at timestamptz not null default now(),
    constraint ck_extraction_stage_event_type check (event_type in ('started','completed','measurement','note','deviation','hold','released')),
    constraint ck_extraction_stage_input check (input_weight_g is null or input_weight_g >= 0),
    constraint ck_extraction_stage_output check (output_weight_g is null or output_weight_g >= 0),
    constraint ck_extraction_stage_loss check (loss_weight_g is null or loss_weight_g >= 0)
);
create index if not exists ix_extraction_stage_events_organization_id on public.extraction_stage_events(organization_id);
create index if not exists ix_extraction_stage_events_facility_id on public.extraction_stage_events(facility_id);
create index if not exists ix_extraction_stage_events_run_id on public.extraction_stage_events(run_id);
create index if not exists ix_extraction_stage_events_machine_id on public.extraction_stage_events(machine_id);
create index if not exists ix_extraction_stage_run_time on public.extraction_stage_events(run_id, occurred_at);

create table if not exists public.extraction_run_outputs (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.extraction_runs(id) on delete cascade,
    product_id varchar(36) not null references public.coman_products(id) on delete restrict,
    lot_id varchar(36) references public.coman_inventory_lots(id) on delete set null,
    position integer not null,
    output_label varchar(255) not null,
    quantity double precision not null,
    unit varchar(32) not null,
    status varchar(24) not null default 'quarantine',
    coa_status varchar(24) not null default 'not_submitted',
    compliance_package_id varchar(255) not null default '',
    output_cost_usd double precision not null default 0,
    notes text not null default '',
    created_by varchar(255) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_extraction_output_run_position unique (run_id, position),
    constraint ck_extraction_output_quantity check (quantity > 0),
    constraint ck_extraction_output_status check (status in ('wip','quarantine','released','waste','destroyed')),
    constraint ck_extraction_output_coa_status check (coa_status in ('not_submitted','pending','passed','failed'))
);
create index if not exists ix_extraction_run_outputs_organization_id on public.extraction_run_outputs(organization_id);
create index if not exists ix_extraction_run_outputs_facility_id on public.extraction_run_outputs(facility_id);
create index if not exists ix_extraction_run_outputs_run_id on public.extraction_run_outputs(run_id);
create index if not exists ix_extraction_run_outputs_product_id on public.extraction_run_outputs(product_id);
create index if not exists ix_extraction_run_outputs_lot_id on public.extraction_run_outputs(lot_id);
create index if not exists ix_extraction_outputs_run_status on public.extraction_run_outputs(run_id, status);

create table if not exists public.extraction_cost_events (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.extraction_runs(id) on delete cascade,
    category varchar(24) not null,
    amount_usd double precision not null,
    quantity double precision,
    unit varchar(32) not null default '',
    unit_rate_usd double precision,
    source_type varchar(64) not null default 'manual',
    source_id varchar(255) not null default '',
    notes text not null default '',
    actor varchar(255) not null,
    occurred_at timestamptz not null default now(),
    constraint ck_extraction_cost_category check (category in ('material','labor','packaging','processing','overhead','waste','other')),
    constraint ck_extraction_cost_amount check (amount_usd >= 0),
    constraint ck_extraction_cost_quantity check (quantity is null or quantity >= 0)
);
create index if not exists ix_extraction_cost_events_organization_id on public.extraction_cost_events(organization_id);
create index if not exists ix_extraction_cost_events_facility_id on public.extraction_cost_events(facility_id);
create index if not exists ix_extraction_cost_events_run_id on public.extraction_cost_events(run_id);
create index if not exists ix_extraction_cost_run_time on public.extraction_cost_events(run_id, occurred_at);

create table if not exists public.extraction_qa_events (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.extraction_runs(id) on delete cascade,
    output_id varchar(36) references public.extraction_run_outputs(id) on delete set null,
    event_type varchar(32) not null,
    result varchar(24) not null default 'pending',
    coa_reference varchar(1024) not null default '',
    deviation_code varchar(120) not null default '',
    notes text not null default '',
    actor varchar(255) not null,
    occurred_at timestamptz not null default now(),
    constraint ck_extraction_qa_event_type check (event_type in ('sample_submitted','coa_attached','hold','release','failure','retest','remediation','deviation')),
    constraint ck_extraction_qa_result check (result in ('pending','passed','failed','not_applicable'))
);
create index if not exists ix_extraction_qa_events_organization_id on public.extraction_qa_events(organization_id);
create index if not exists ix_extraction_qa_events_facility_id on public.extraction_qa_events(facility_id);
create index if not exists ix_extraction_qa_events_run_id on public.extraction_qa_events(run_id);
create index if not exists ix_extraction_qa_events_output_id on public.extraction_qa_events(output_id);
create index if not exists ix_extraction_qa_run_time on public.extraction_qa_events(run_id, occurred_at);

create table if not exists public.extraction_toll_jobs (
    id varchar(36) primary key,
    organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
    run_id varchar(36) not null references public.extraction_runs(id) on delete cascade,
    customer_id varchar(36) not null references public.coman_customers(id) on delete restrict,
    promised_completion_at timestamptz,
    processing_fee_usd double precision not null default 0,
    invoice_status varchar(24) not null default 'draft',
    payment_status varchar(24) not null default 'pending',
    external_reference varchar(255) not null default '',
    notes text not null default '',
    created_by varchar(255) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_extraction_toll_run unique (run_id),
    constraint ck_extraction_toll_fee check (processing_fee_usd >= 0),
    constraint ck_extraction_toll_invoice_status check (invoice_status in ('draft','sent','paid','overdue')),
    constraint ck_extraction_toll_payment_status check (payment_status in ('pending','partial','paid'))
);
create index if not exists ix_extraction_toll_jobs_organization_id on public.extraction_toll_jobs(organization_id);
create index if not exists ix_extraction_toll_jobs_facility_id on public.extraction_toll_jobs(facility_id);
create index if not exists ix_extraction_toll_jobs_run_id on public.extraction_toll_jobs(run_id);
create index if not exists ix_extraction_toll_jobs_customer_id on public.extraction_toll_jobs(customer_id);

alter table public.extraction_runs enable row level security;
alter table public.extraction_run_inputs enable row level security;
alter table public.extraction_stage_events enable row level security;
alter table public.extraction_run_outputs enable row level security;
alter table public.extraction_cost_events enable row level security;
alter table public.extraction_qa_events enable row level security;
alter table public.extraction_toll_jobs enable row level security;

comment on table public.extraction_runs is 'Tenant/facility-scoped extraction production runs. Streamlit session state is cache only.';
comment on table public.extraction_stage_events is 'Append-only stage history for extraction mass balance, deviations, holds, and operator notes.';
comment on table public.extraction_cost_events is 'Append-only extraction COGS ledger for materials, labor, packaging, processing, overhead, and waste.';

update public.alembic_version
set version_num = '0021_extraction_erp'
where version_num = '0020_product_master';
