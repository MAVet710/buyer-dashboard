alter table coman_facilities add column if not exists license_number varchar(160) not null default '';
alter table coman_facilities add column if not exists license_type varchar(120) not null default '';
alter table coman_facilities add column if not exists retail_enabled boolean not null default true;
alter table coman_facilities add column if not exists production_enabled boolean not null default true;
alter table coman_facilities add column if not exists cultivation_enabled boolean not null default false;
alter table coman_facilities add column if not exists commercial_enabled boolean not null default true;
update alembic_version set version_num = '0035_facility_capabilities' where version_num = '0034_integrations';
