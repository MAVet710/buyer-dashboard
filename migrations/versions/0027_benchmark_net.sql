-- Privacy-safe benchmark network. Apply after 0026_doobie_actions.

create table if not exists public.benchmark_settings (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 share_anonymized_aggregates boolean not null default false,
 minimum_cohort_size integer not null default 5,
 updated_by varchar(255) not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_benchmark_setting_org unique(organization_id),
 constraint ck_benchmark_min_cohort check (minimum_cohort_size >= 3 and minimum_cohort_size <= 50)
);
create index if not exists ix_benchmark_settings_organization_id on public.benchmark_settings(organization_id);

create table if not exists public.benchmark_observations (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete cascade,
 metric_key varchar(120) not null, cohort_key varchar(160) not null default 'all',
 value double precision not null, unit varchar(32) not null, sample_count integer not null,
 period_start date not null, period_end date not null, captured_at timestamptz not null default now(),
 constraint uq_benchmark_observation_period unique(facility_id,metric_key,cohort_key,period_start,period_end),
 constraint ck_benchmark_sample_count check (sample_count >= 1)
);
create index if not exists ix_benchmark_observations_organization_id on public.benchmark_observations(organization_id);
create index if not exists ix_benchmark_observations_facility_id on public.benchmark_observations(facility_id);
create index if not exists ix_benchmark_metric_cohort_period on public.benchmark_observations(metric_key,cohort_key,period_end);

alter table public.benchmark_settings enable row level security;
alter table public.benchmark_observations enable row level security;

update public.alembic_version set version_num='0027_benchmark_net' where version_num='0026_doobie_actions';
