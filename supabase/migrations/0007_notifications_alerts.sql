-- Make in-app notifications and urgent alerts enforce their Phase 1 contracts.

alter table public.profiles
  add column if not exists display_name text,
  add column if not exists is_on_duty boolean not null default true;

update public.profiles
set display_name = case id
  when '00000000-0000-0000-0000-000000000001' then 'Worker Tan'
  when '00000000-0000-0000-0000-000000000002' then '王师傅'
  when '00000000-0000-0000-0000-000000000003' then 'Lim Wei Sheng'
  when '00000000-0000-0000-0000-000000000004' then 'Ah Hock'
  when '00000000-0000-0000-0000-000000000005' then 'Crew Member'
  when '00000000-0000-0000-0000-000000000006' then 'Site Admin'
  else 'Site user ' || left(id::text, 8)
end
where display_name is null or btrim(display_name) = '';

alter table public.profiles alter column display_name set not null;

do $$
begin
  alter table public.profiles
    add constraint profiles_display_name_nonempty check (btrim(display_name) <> '');
exception when duplicate_object then null;
end $$;

create or replace function public.handle_auth_user_profile() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into profiles (id, role, preferred_lang, display_name)
  values (
    new.id,
    'reporter',
    'en',
    coalesce(
      nullif(btrim(new.raw_user_meta_data ->> 'full_name'), ''),
      nullif(btrim(new.raw_user_meta_data ->> 'name'), ''),
      nullif(split_part(coalesce(new.email, ''), '@', 1), ''),
      'Site user ' || left(new.id::text, 8)
    )
  )
  on conflict (id) do nothing;
  return new;
end $$;

create or replace function public.notification_payload_data_only(payload jsonb)
returns boolean
language plpgsql
immutable
as $$
declare
  child jsonb;
  payload_type text := jsonb_typeof(payload);
begin
  if payload_type in ('number', 'null') then
    return true;
  end if;
  if payload_type = 'string' then
    return (payload #>> '{}') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$';
  end if;
  if payload_type = 'array' then
    for child in select value from jsonb_array_elements(payload) loop
      if not public.notification_payload_data_only(child) then
        return false;
      end if;
    end loop;
    return true;
  end if;
  if payload_type = 'object' then
    for child in select value from jsonb_each(payload) loop
      if not public.notification_payload_data_only(child) then
        return false;
      end if;
    end loop;
    return true;
  end if;
  return false;
end $$;

do $$
begin
  alter table public.notifications
    add constraint notifications_kind_valid check (
      kind in (
        'assigned', 'sent_back', 'overdue', 'info_requested',
        'alert_raised', 'briefing_published', 'report_closed'
      )
    );
exception when duplicate_object then null;
end $$;

alter table public.notifications
  drop constraint if exists notifications_payload_data_only;

alter table public.notifications
  add constraint notifications_payload_data_only check (
    jsonb_typeof(payload) = 'object'
    and public.notification_payload_data_only(payload)
  );

do $$
begin
  alter table public.alerts
    add constraint alerts_acknowledgement_complete check (
      (acknowledged_by is null) = (acknowledged_at is null)
    );
exception when duplicate_object then null;
end $$;

do $$
begin
  alter table public.alerts
    add constraint alerts_resolution_nonempty check (
      resolution_note is null or btrim(resolution_note) <> ''
    );
exception when duplicate_object then null;
end $$;

create unique index if not exists alerts_one_per_report
  on public.alerts (report_id);

create index if not exists notifications_unread_first
  on public.notifications (recipient_id, (read_at is null) desc, created_at desc, id desc);

create index if not exists alerts_live_first
  on public.alerts (
    (resolution_note is null) desc,
    (acknowledged_at is null) desc,
    raised_at desc,
    id desc
  );
