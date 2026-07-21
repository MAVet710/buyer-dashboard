create table if not exists public.coman_hand_labor_areas (
 id varchar(36) primary key, organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete cascade, name varchar(255) not null default 'Primary Hand Labor Area',
 default_crew_size integer not null default 1, sticker_units_per_person_hour double precision not null default 0 check (sticker_units_per_person_hour >= 0),
 case_pack_units_per_person_hour double precision not null default 0 check (case_pack_units_per_person_hour >= 0), final_cases_per_person_hour double precision not null default 0 check (final_cases_per_person_hour >= 0),
 setup_minutes integer not null default 0, cleanup_minutes integer not null default 0, active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), constraint uq_coman_hand_labor_area_name unique (facility_id, name));
create index if not exists ix_coman_hand_labor_areas_organization_id on public.coman_hand_labor_areas(organization_id);
create index if not exists ix_coman_hand_labor_areas_facility_id on public.coman_hand_labor_areas(facility_id);
alter table public.coman_hand_labor_areas enable row level security;
