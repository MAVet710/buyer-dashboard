begin;

create table alembic_version (
    version_num varchar(32) primary key
);

create table coman_organizations (
    id varchar(36) primary key,
    name varchar(255) not null,
    slug varchar(120) not null unique,
    active boolean not null,
    created_at timestamptz not null,
    updated_at timestamptz not null
);

create table coman_machine_models (
    id varchar(36) primary key,
    manufacturer varchar(255) not null,
    model varchar(255) not null,
    category varchar(120) not null,
    operations_json text not null,
    published_max_rate double precision not null,
    rate_unit varchar(64) not null,
    published_min_operators integer,
    published_max_operators integer,
    planning_utilization_pct double precision not null,
    source_url varchar(1024) not null,
    source_checked_at timestamptz,
    active boolean not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_coman_machine_make_model unique (manufacturer, model),
    constraint ck_coman_machine_rate_nonnegative check (published_max_rate >= 0)
);

create table coman_facilities (
    id varchar(36) primary key,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    name varchar(255) not null,
    code varchar(64) not null,
    timezone_name varchar(64) not null,
    active boolean not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_coman_facility_org_code unique (organization_id, code)
);
create index ix_coman_facilities_organization_id on coman_facilities (organization_id);

create table coman_customers (
    id varchar(36) primary key,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    name varchar(255) not null,
    license_or_registration varchar(255) not null,
    contact_name varchar(255) not null,
    contact_email varchar(320) not null,
    active boolean not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_coman_customer_org_name unique (organization_id, name)
);
create index ix_coman_customers_organization_id on coman_customers (organization_id);

create table coman_facility_machines (
    id varchar(36) primary key,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references coman_facilities(id) on delete cascade,
    machine_model_id varchar(36) not null references coman_machine_models(id) on delete restrict,
    asset_code varchar(120) not null,
    display_name varchar(255) not null,
    effective_rate double precision not null,
    rate_unit varchar(64) not null,
    preferred_crew_size integer not null,
    setup_minutes integer not null,
    cleanup_minutes integer not null,
    active boolean not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_coman_facility_machine_asset unique (facility_id, asset_code),
    constraint ck_coman_facility_machine_rate_nonnegative check (effective_rate >= 0)
);
create index ix_coman_facility_machines_facility_id on coman_facility_machines (facility_id);
create index ix_coman_facility_machines_organization_id on coman_facility_machines (organization_id);

create table coman_production_orders (
    id varchar(36) primary key,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references coman_facilities(id) on delete restrict,
    customer_id varchar(36) references coman_customers(id) on delete restrict,
    order_number varchar(64) not null,
    work_type varchar(16) not null,
    product_name varchar(255) not null,
    sku varchar(120) not null,
    product_format varchar(120) not null,
    requested_units integer not null,
    due_at timestamptz,
    priority varchar(32) not null,
    status varchar(32) not null,
    source_lot_reference varchar(255) not null,
    material_owner varchar(255) not null,
    packaging_owner varchar(255) not null,
    notes text not null,
    created_by varchar(255) not null,
    updated_by varchar(255) not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_coman_order_org_number unique (organization_id, order_number),
    constraint ck_coman_order_units_nonnegative check (requested_units >= 0),
    constraint ck_coman_order_work_type check (work_type in ('internal', 'external'))
);
create index ix_coman_production_orders_customer_id on coman_production_orders (customer_id);
create index ix_coman_production_orders_facility_id on coman_production_orders (facility_id);
create index ix_coman_production_orders_organization_id on coman_production_orders (organization_id);
create index ix_coman_orders_facility_status_due on coman_production_orders (facility_id, status, due_at);

create table coman_audit_events (
    id varchar(36) primary key,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    facility_id varchar(36) references coman_facilities(id) on delete set null,
    entity_type varchar(120) not null,
    entity_id varchar(36) not null,
    action varchar(120) not null,
    actor varchar(255) not null,
    changes_json text not null,
    occurred_at timestamptz not null
);
create index ix_coman_audit_events_organization_id on coman_audit_events (organization_id);
create index ix_coman_audit_entity on coman_audit_events (organization_id, entity_type, entity_id);

alter table coman_organizations enable row level security;
alter table coman_facilities enable row level security;
alter table coman_customers enable row level security;
alter table coman_machine_models enable row level security;
alter table coman_facility_machines enable row level security;
alter table coman_production_orders enable row level security;
alter table coman_audit_events enable row level security;

insert into coman_machine_models (
    id, manufacturer, model, category, operations_json, published_max_rate,
    rate_unit, published_min_operators, published_max_operators,
    planning_utilization_pct, source_url, source_checked_at, active, created_at, updated_at
) values
(
    '46ea9f9f-e075-4dc4-b80d-a46769440001', 'IMA', 'C-1 FILLER',
    'pre-roll filling and closing', '["cone filling", "compaction", "twisting", "vision inspection"]',
    80.0, 'units/minute', null, null, 65.0,
    'https://imagroup.com/machines/c-1-filler/', '2026-07-20 00:00:00+00', true,
    '2026-07-20 00:00:00+00', '2026-07-20 00:00:00+00'
),
(
    '46ea9f9f-e075-4dc4-b80d-a46769440002', 'IMA', 'C-1 MAKER',
    'pre-roll cone making', '["filter folding", "paper cutting", "cone rolling", "vision inspection"]',
    200.0, 'cones/minute', null, null, 65.0,
    'https://imagroup.com/machines/c-1-maker/', '2026-07-20 00:00:00+00', true,
    '2026-07-20 00:00:00+00', '2026-07-20 00:00:00+00'
),
(
    '46ea9f9f-e075-4dc4-b80d-a46769440003', 'Massman / General Packer', 'GP-M3000',
    'flower pouch packaging', '["pouch feeding", "opening", "filling", "settling", "heat sealing"]',
    65.0, 'pouches/minute', 2, 2, 65.0,
    'https://massmanautomation.com/revolutionizing-cannabis-packaging-the-gp-m3000-machine/',
    '2026-07-20 00:00:00+00', true, '2026-07-20 00:00:00+00', '2026-07-20 00:00:00+00'
);

insert into alembic_version (version_num) values ('0001_coman_foundation');

commit;
