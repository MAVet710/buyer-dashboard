create table if not exists public.coman_production_actuals (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete cascade,
 production_order_id varchar(36) not null references public.coman_production_orders(id) on delete cascade,
 actual_units integer not null default 0 check(actual_units >= 0), scrap_units integer not null default 0 check(scrap_units >= 0),
 rework_units integer not null default 0 check(rework_units >= 0), actual_machine_hours double precision not null default 0,
 actual_labor_hours double precision not null default 0, completed_at timestamptz, notes text not null default '', recorded_by varchar(255) not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), constraint uq_coman_actual_order unique(production_order_id));
create index if not exists ix_coman_production_actuals_organization_id on public.coman_production_actuals(organization_id);
create index if not exists ix_coman_production_actuals_facility_id on public.coman_production_actuals(facility_id);
create index if not exists ix_coman_production_actuals_production_order_id on public.coman_production_actuals(production_order_id);
alter table public.coman_production_actuals enable row level security;
