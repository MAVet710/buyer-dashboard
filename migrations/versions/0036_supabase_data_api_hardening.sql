-- Buyer Dash operational data is accessed only through FastAPI. The browser
-- receives a Supabase publishable key for Auth, never direct table access.
do $$
declare
  table_record record;
  role_name text;
begin
  for table_record in
    select schemaname, tablename from pg_tables
    where schemaname = 'public' and tablename <> 'alembic_version'
  loop
    execute format('alter table %I.%I enable row level security', table_record.schemaname, table_record.tablename);
  end loop;
  foreach role_name in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = role_name) then
      execute format('revoke all privileges on all tables in schema public from %I', role_name);
      execute format('revoke all privileges on all sequences in schema public from %I', role_name);
      execute format('alter default privileges in schema public revoke all on tables from %I', role_name);
      execute format('alter default privileges in schema public revoke all on sequences from %I', role_name);
    end if;
  end loop;
end $$;
update alembic_version set version_num = '0036_supabase_data_api_hardening' where version_num = '0035_facility_capabilities';
