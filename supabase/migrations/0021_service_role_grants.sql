-- The service-role key is a server-side administrative credential. Supabase's
-- PostgREST API still requires object privileges even though this role bypasses
-- row-level security, so grant those privileges explicitly after the RLS
-- migration revokes browser-role access.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    raise notice 'Supabase service_role unavailable; administrative grants skipped';
    return;
  end if;

  execute 'grant usage on schema public to service_role';
  execute 'grant all privileges on all tables in schema public to service_role';
  execute 'grant all privileges on all sequences in schema public to service_role';
  execute 'grant execute on all functions in schema public to service_role';
  execute 'alter default privileges in schema public '
    'grant all privileges on tables to service_role';
  execute 'alter default privileges in schema public '
    'grant all privileges on sequences to service_role';
  execute 'alter default privileges in schema public '
    'grant execute on functions to service_role';
end
$$;
