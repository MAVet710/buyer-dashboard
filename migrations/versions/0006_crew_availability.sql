create table if not exists public.coman_crew_availability (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete cascade, work_date date not null,
 shift_name varchar(120) not null default 'Day', available_people integer not null default 0 check(available_people >= 0),
 shift_hours double precision not null default 8 check(shift_hours > 0), notes text not null default '', updated_by varchar(255) not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), constraint uq_coman_crew_facility_date_shift unique(facility_id, work_date, shift_name));
create index if not exists ix_coman_crew_availability_organization_id on public.coman_crew_availability(organization_id);
create index if not exists ix_coman_crew_availability_facility_id on public.coman_crew_availability(facility_id);
create index if not exists ix_coman_crew_availability_work_date on public.coman_crew_availability(work_date);
alter table public.coman_crew_availability enable row level security;
