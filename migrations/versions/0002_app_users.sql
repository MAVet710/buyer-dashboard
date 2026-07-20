begin;

create table app_users (
    id varchar(36) primary key,
    organization_id varchar(36) references coman_organizations(id) on delete set null,
    username varchar(120) not null,
    normalized_username varchar(120) not null unique,
    display_name varchar(255) not null,
    email varchar(320) not null,
    password_hash varchar(255) not null,
    role varchar(32) not null,
    active boolean not null,
    must_change_password boolean not null,
    last_login_at timestamptz,
    password_changed_at timestamptz,
    created_by varchar(255) not null,
    updated_by varchar(255) not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint ck_app_users_role check (
        role in ('admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')
    )
);
create index ix_app_users_org_active on app_users (organization_id, active);

create table app_user_facility_roles (
    id varchar(36) primary key,
    user_id varchar(36) not null references app_users(id) on delete cascade,
    organization_id varchar(36) not null references coman_organizations(id) on delete cascade,
    facility_id varchar(36) not null references coman_facilities(id) on delete cascade,
    role varchar(32) not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    constraint uq_app_user_facility unique (user_id, facility_id),
    constraint ck_app_user_facility_role check (
        role in ('admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')
    )
);
create index ix_app_user_facility_roles_organization_id on app_user_facility_roles (organization_id);
create index ix_app_user_facility_roles_user_id on app_user_facility_roles (user_id);
create index ix_app_user_facility_roles_facility_id on app_user_facility_roles (facility_id);

alter table app_users enable row level security;
alter table app_user_facility_roles enable row level security;

update alembic_version
set version_num = '0002_app_users'
where version_num = '0001_coman_foundation';

commit;
