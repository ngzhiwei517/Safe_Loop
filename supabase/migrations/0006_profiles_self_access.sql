-- Let signed-in users read their own profile and update only their language.

alter table public.profiles enable row level security;

revoke all privileges on table public.profiles from anon;
revoke all privileges on table public.profiles from authenticated;

grant select on table public.profiles to authenticated;
grant update (preferred_lang) on table public.profiles to authenticated;

drop policy if exists profiles_select_self on public.profiles;
create policy profiles_select_self on public.profiles
  for select
  to authenticated
  using ((select auth.uid()) = id);

drop policy if exists profiles_update_preferred_lang_self on public.profiles;
create policy profiles_update_preferred_lang_self on public.profiles
  for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);
