-- Link application profiles to Supabase Auth while preserving Phase 0 seed fixtures.

alter table profiles
  add constraint profiles_auth_user_fk
  foreign key (id) references auth.users(id)
  not valid;

create or replace function handle_auth_user_profile() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into profiles (id, role, preferred_lang)
  values (new.id, 'reporter', 'en')
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_auth_user_profile();
