-- Generic production execution, QA and COGS. Apply after 0023_switch_center.

create table if not exists public.production_run_events (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 production_order_id varchar(36) not null references public.coman_production_orders(id) on delete cascade,
 stage_key varchar(120) not null default 'execution', event_type varchar(24) not null,
 quantity double precision, unit varchar(32) not null default 'unit', waste_quantity double precision,
 labor_hours double precision, machine_hours double precision,
 machine_id varchar(36) references public.coman_facility_machines(id) on delete set null,
 notes text not null default '', actor varchar(255) not null, occurred_at timestamptz not null default now(),
 constraint ck_production_run_event_type check (event_type in ('started','completed','measurement','hold','release','rework','waste','note')),
 constraint ck_production_run_event_qty check (quantity is null or quantity >= 0),
 constraint ck_production_run_event_waste check (waste_quantity is null or waste_quantity >= 0),
 constraint ck_production_run_event_labor check (labor_hours is null or labor_hours >= 0),
 constraint ck_production_run_event_machine check (machine_hours is null or machine_hours >= 0)
);
create index if not exists ix_production_run_events_organization_id on public.production_run_events(organization_id);
create index if not exists ix_production_run_events_facility_id on public.production_run_events(facility_id);
create index if not exists ix_production_run_events_production_order_id on public.production_run_events(production_order_id);
create index if not exists ix_production_run_events_machine_id on public.production_run_events(machine_id);
create index if not exists ix_production_run_event_order_time on public.production_run_events(production_order_id,occurred_at);

create table if not exists public.production_run_outputs (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 production_order_id varchar(36) not null references public.coman_production_orders(id) on delete cascade,
 product_id varchar(36) not null references public.coman_products(id) on delete restrict,
 lot_id varchar(36) references public.coman_inventory_lots(id) on delete set null,
 position integer not null, label varchar(255) not null,
 planned_quantity double precision not null default 0, actual_quantity double precision not null default 0,
 unit varchar(32) not null default 'unit', status varchar(24) not null default 'planned',
 created_by varchar(255) not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_production_run_output_position unique(production_order_id,position),
 constraint ck_production_output_planned check (planned_quantity >= 0),
 constraint ck_production_output_actual check (actual_quantity >= 0),
 constraint ck_production_output_status check (status in ('planned','wip','quarantine','released','rework','waste','destroyed'))
);
create index if not exists ix_production_run_outputs_organization_id on public.production_run_outputs(organization_id);
create index if not exists ix_production_run_outputs_facility_id on public.production_run_outputs(facility_id);
create index if not exists ix_production_run_outputs_production_order_id on public.production_run_outputs(production_order_id);
create index if not exists ix_production_run_outputs_product_id on public.production_run_outputs(product_id);
create index if not exists ix_production_run_outputs_lot_id on public.production_run_outputs(lot_id);
create index if not exists ix_production_output_order_status on public.production_run_outputs(production_order_id,status);

create table if not exists public.production_cost_events (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 production_order_id varchar(36) not null references public.coman_production_orders(id) on delete cascade,
 category varchar(24) not null, amount_usd double precision not null, quantity double precision,
 unit varchar(32) not null default '', source_type varchar(64) not null default 'manual', source_id varchar(255) not null default '',
 notes text not null default '', actor varchar(255) not null, occurred_at timestamptz not null default now(),
 constraint ck_production_cost_category check (category in ('material','labor','packaging','machine','overhead','waste','other')),
 constraint ck_production_cost_amount check (amount_usd >= 0)
);
create index if not exists ix_production_cost_events_organization_id on public.production_cost_events(organization_id);
create index if not exists ix_production_cost_events_facility_id on public.production_cost_events(facility_id);
create index if not exists ix_production_cost_events_production_order_id on public.production_cost_events(production_order_id);
create index if not exists ix_production_cost_order_time on public.production_cost_events(production_order_id,occurred_at);

create table if not exists public.production_qa_events (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 production_order_id varchar(36) not null references public.coman_production_orders(id) on delete cascade,
 output_id varchar(36) references public.production_run_outputs(id) on delete set null,
 event_type varchar(24) not null, result varchar(24) not null default 'pending',
 document_reference varchar(1024) not null default '', notes text not null default '', actor varchar(255) not null,
 occurred_at timestamptz not null default now(),
 constraint ck_production_qa_event_type check (event_type in ('hold','sample','pass','fail','release','retest','deviation','remediation')),
 constraint ck_production_qa_result check (result in ('pending','passed','failed','not_applicable'))
);
create index if not exists ix_production_qa_events_organization_id on public.production_qa_events(organization_id);
create index if not exists ix_production_qa_events_facility_id on public.production_qa_events(facility_id);
create index if not exists ix_production_qa_events_production_order_id on public.production_qa_events(production_order_id);
create index if not exists ix_production_qa_events_output_id on public.production_qa_events(output_id);
create index if not exists ix_production_qa_order_time on public.production_qa_events(production_order_id,occurred_at);

alter table public.production_run_events enable row level security;
alter table public.production_run_outputs enable row level security;
alter table public.production_cost_events enable row level security;
alter table public.production_qa_events enable row level security;

update public.alembic_version set version_num='0024_production_erp' where version_num='0023_switch_center';
