create table if not exists cultivation_plants (
    id varchar(36) primary key,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references coman_facilities(id) on delete restrict,
    plant_tag varchar(255) not null,
    strain_name varchar(255) not null,
    phase varchar(24) not null check (phase in ('clone','seedling','vegetative','flowering','harvested','destroyed')),
    room_code varchar(120) not null default 'UNASSIGNED',
    source_lot_id varchar(36) references coman_inventory_lots(id) on delete set null,
    mother_plant_tag varchar(255) not null default '',
    planted_at date,
    estimated_harvest_date date,
    retired_at timestamptz,
    notes text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_cultivation_plant_facility_tag unique (facility_id, plant_tag)
);
create index if not exists ix_cultivation_plants_org on cultivation_plants(organization_id);
create index if not exists ix_cultivation_plants_facility_phase on cultivation_plants(facility_id, phase);
create index if not exists ix_cultivation_plants_source_lot on cultivation_plants(source_lot_id);

create table if not exists cultivation_plant_events (
    id varchar(36) primary key,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references coman_facilities(id) on delete restrict,
    plant_id varchar(36) not null references cultivation_plants(id) on delete restrict,
    event_type varchar(40) not null,
    from_value varchar(255) not null default '',
    to_value varchar(255) not null default '',
    reason varchar(255) not null default '',
    notes text not null default '',
    actor varchar(255) not null,
    occurred_at timestamptz not null default now()
);
create index if not exists ix_cultivation_plant_events_org on cultivation_plant_events(organization_id);
create index if not exists ix_cultivation_plant_events_facility on cultivation_plant_events(facility_id);
create index if not exists ix_cultivation_plant_events_plant_time on cultivation_plant_events(plant_id, occurred_at);
alter table cultivation_plants enable row level security;
alter table cultivation_plant_events enable row level security;
