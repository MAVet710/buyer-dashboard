create table if not exists public.retail_sales (
 id varchar(36) primary key,
 organization_id varchar(36) not null references public.coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references public.coman_facilities(id) on delete restrict,
 product_id varchar(36) references public.coman_products(id) on delete set null,
 source_system varchar(64) not null, source_record_id varchar(255) not null,
 import_batch_id varchar(64) not null default '', sku varchar(120) not null default '',
 product_name varchar(255) not null, quantity double precision not null,
 net_sales double precision not null default 0, sold_at timestamptz not null,
 imported_by varchar(255) not null, created_at timestamptz not null default now(),
 constraint uq_retail_sale_source_record unique(organization_id, facility_id, source_system, source_record_id)
);
create index if not exists ix_retail_sales_facility_time on public.retail_sales(facility_id, sold_at);
create index if not exists ix_retail_sales_product_time on public.retail_sales(product_id, sold_at);
create index if not exists ix_retail_sales_organization_id on public.retail_sales(organization_id);
alter table public.retail_sales enable row level security;
update public.alembic_version set version_num='0030_retail_sales_ledger' where version_num='0029_dev_sandbox_ledger_reset';
