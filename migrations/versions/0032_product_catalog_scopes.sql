alter table product_master_profiles add column if not exists retail_enabled boolean not null default true;
alter table product_master_profiles add column if not exists production_enabled boolean not null default true;
update alembic_version set version_num = '0032_product_catalog_scopes' where version_num = '0031_cultivation_plants';
