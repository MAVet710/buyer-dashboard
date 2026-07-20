begin;

alter table app_user_facility_roles drop constraint ck_app_user_facility_role;
alter table app_users drop constraint ck_app_users_role;
alter table app_users add constraint ck_app_users_role check (
    role in ('dev', 'admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')
);
alter table app_user_facility_roles add constraint ck_app_user_facility_role check (
    role in ('dev', 'admin', 'buyer', 'planner', 'supervisor', 'operator', 'qa', 'read_only')
);

update app_users
set role = 'dev', organization_id = null, updated_by = '0003_level_dev'
where normalized_username = 'god';

update alembic_version set version_num = '0003_level_dev' where version_num = '0002_app_users';

commit;
