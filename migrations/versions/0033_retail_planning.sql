create table if not exists retail_planning_policies (
 id varchar(36) primary key, organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
 facility_id varchar(36) not null references coman_facilities(id) on delete cascade, product_id varchar(36) not null references coman_products(id) on delete cascade,
 preferred_vendor_id varchar(36) references commercial_trade_partners(id) on delete set null, target_doh double precision not null default 30,
 safety_stock double precision not null default 0, reorder_point double precision not null default 0, minimum_order_quantity double precision not null default 0,
 case_pack double precision not null default 0, velocity_window_days integer not null default 30, active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(facility_id, product_id),
 check(target_doh >= 0), check(safety_stock >= 0), check(minimum_order_quantity >= 0), check(case_pack >= 0), check(velocity_window_days between 7 and 180)
);
create index if not exists ix_retail_planning_org_facility_active on retail_planning_policies(organization_id, facility_id, active);
alter table retail_planning_policies enable row level security;
update alembic_version set version_num = '0033_retail_planning' where version_num = '0032_product_catalog_scopes';
