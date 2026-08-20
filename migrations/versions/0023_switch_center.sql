-- Switch to Buyer Dash migration command center. Apply after 0022_extraction_intel.

create table if not exists public.migration_batches (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 source_system varchar(24) not null,
 entity_type varchar(24) not null,
 filename varchar(512) not null default '', fingerprint varchar(64) not null default '',
 status varchar(24) not null default 'staged', total_records integer not null default 0,
 matched_records integer not null default 0, review_records integer not null default 0,
 unmapped_records integer not null default 0, conflict_records integer not null default 0,
 committed_records integer not null default 0, created_by varchar(255) not null, notes text not null default '',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint ck_migration_batch_source check (source_system in ('dutchie','distru','metrc','spreadsheet','other')),
 constraint ck_migration_batch_entity check (entity_type in ('product','vendor','inventory','sales')),
 constraint ck_migration_batch_status check (status in ('staged','review','ready','committed','cancelled','failed'))
);
create index if not exists ix_migration_batches_organization_id on public.migration_batches(organization_id);
create index if not exists ix_migration_batches_facility_id on public.migration_batches(facility_id);
create index if not exists ix_migration_batch_facility_status on public.migration_batches(facility_id,status,created_at);

create table if not exists public.migration_records (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 batch_id varchar(36) not null references public.migration_batches(id) on delete cascade,
 source_row_number integer not null, source_external_id varchar(255) not null default '', entity_type varchar(24) not null,
 source_json text not null default '{}', normalized_json text not null default '{}',
 match_status varchar(24) not null default 'unmapped', confidence double precision not null default 0,
 canonical_entity_id varchar(36) not null default '', match_reason varchar(255) not null default '',
 decision_action varchar(24) not null default 'pending', reviewed_by varchar(255) not null default '',
 reviewed_at timestamptz, committed_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint uq_migration_record_batch_row unique(batch_id,source_row_number),
 constraint ck_migration_record_match_status check (match_status in ('auto_match','review_required','unmapped','conflict','committed','skipped')),
 constraint ck_migration_record_decision check (decision_action in ('pending','accept','create','link','skip')),
 constraint ck_migration_record_confidence check (confidence >= 0 and confidence <= 1)
);
create index if not exists ix_migration_records_organization_id on public.migration_records(organization_id);
create index if not exists ix_migration_records_facility_id on public.migration_records(facility_id);
create index if not exists ix_migration_records_batch_id on public.migration_records(batch_id);
create index if not exists ix_migration_record_batch_status on public.migration_records(batch_id,match_status,source_row_number);

create table if not exists public.migration_sales_history (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 product_id varchar(36) not null references public.coman_products(id) on delete restrict,
 source_system varchar(24) not null, source_external_id varchar(255) not null,
 sale_date date not null, units double precision not null default 0, revenue double precision not null default 0,
 source_record_id varchar(36) references public.migration_records(id) on delete set null,
 imported_at timestamptz not null default now(),
 constraint uq_migration_sales_source unique(organization_id,source_system,source_external_id),
 constraint ck_migration_sales_units check (units >= 0), constraint ck_migration_sales_revenue check (revenue >= 0)
);
create index if not exists ix_migration_sales_history_organization_id on public.migration_sales_history(organization_id);
create index if not exists ix_migration_sales_history_facility_id on public.migration_sales_history(facility_id);
create index if not exists ix_migration_sales_history_product_id on public.migration_sales_history(product_id);
create index if not exists ix_migration_sales_history_source_record_id on public.migration_sales_history(source_record_id);
create index if not exists ix_migration_sales_product_date on public.migration_sales_history(product_id,sale_date);
create index if not exists ix_migration_sales_facility_date on public.migration_sales_history(facility_id,sale_date);

alter table public.migration_batches enable row level security;
alter table public.migration_records enable row level security;
alter table public.migration_sales_history enable row level security;

update public.alembic_version set version_num='0023_switch_center' where version_num='0022_extraction_intel';
