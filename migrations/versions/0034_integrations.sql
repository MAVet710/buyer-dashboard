create table if not exists integration_configurations (
 id varchar(36) primary key, organization_id varchar(36) references coman_organizations(id) on delete cascade, facility_id varchar(36) references coman_facilities(id) on delete cascade,
 scope_type varchar(24) not null check(scope_type in ('user','facility','platform')), scope_key varchar(255) not null, provider varchar(32) not null check(provider in ('metrc','doobie')),
 configuration_json text not null default '{}', encrypted_secret text not null default '', secret_hint varchar(32) not null default '',
 status varchar(32) not null default 'not_connected' check(status in ('not_connected','configured','connected','failed')), last_validated_at timestamptz,
 last_error varchar(512) not null default '', updated_by varchar(255) not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(scope_type, scope_key, provider)
);
create index if not exists ix_integration_org_facility on integration_configurations(organization_id, facility_id);
alter table integration_configurations enable row level security;
update alembic_version set version_num = '0034_integrations' where version_num = '0033_retail_planning';
