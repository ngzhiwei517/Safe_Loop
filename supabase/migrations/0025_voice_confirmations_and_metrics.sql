-- Track every ASR attempt and every human-confirmed use of a transcript.

create table if not exists public.transcription_attempts (
  id uuid primary key default gen_random_uuid(),
  media_id uuid not null references public.report_media(id) on delete cascade,
  report_id uuid not null references public.reports(id) on delete cascade,
  transcript_id uuid references public.transcripts(id) on delete cascade,
  provider text not null,
  model text not null,
  hint_locale text not null,
  detected_locale text,
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  usable boolean not null,
  failure_code text,
  latency_ms integer not null check (latency_ms >= 0),
  created_at timestamptz not null default now(),
  check ((usable and transcript_id is not null and failure_code is null) or not usable)
);

create index if not exists transcription_attempts_locale_created_at
  on public.transcription_attempts ((coalesce(detected_locale, hint_locale)), created_at desc);

create table if not exists public.transcript_confirmations (
  id uuid primary key default gen_random_uuid(),
  transcript_id uuid not null unique references public.transcripts(id) on delete cascade,
  report_id uuid not null references public.reports(id) on delete cascade,
  context text not null check (
    context in ('report_description', 'clarification_answer', 'action_completion')
  ),
  context_id uuid not null,
  confirmed_text text not null check (btrim(confirmed_text) <> ''),
  input_mode public.input_mode not null check (input_mode <> 'typed'::public.input_mode),
  created_at timestamptz not null default now(),
  unique (context, context_id)
);

create index if not exists transcript_confirmations_report_created_at
  on public.transcript_confirmations (report_id, created_at desc);

create or replace function public.voice_telemetry_no_update() returns trigger
language plpgsql as $$
begin
  raise exception 'voice telemetry is append-only' using errcode = '42501';
end $$;

drop trigger if exists transcription_attempts_no_update on public.transcription_attempts;
create trigger transcription_attempts_no_update before update on public.transcription_attempts
for each row execute function public.voice_telemetry_no_update();

drop trigger if exists transcript_confirmations_no_update on public.transcript_confirmations;
create trigger transcript_confirmations_no_update before update on public.transcript_confirmations
for each row execute function public.voice_telemetry_no_update();

alter table public.transcription_attempts enable row level security;
alter table public.transcript_confirmations enable row level security;
revoke all privileges on public.transcription_attempts from public, anon, authenticated;
revoke all privileges on public.transcript_confirmations from public, anon, authenticated;
grant select on public.transcription_attempts to authenticated;
grant select on public.transcript_confirmations to authenticated;

create policy transcription_attempts_select_visible_report
on public.transcription_attempts for select to authenticated
using (public.safeloop_can_read_report(report_id));

create policy transcript_confirmations_select_visible_report
on public.transcript_confirmations for select to authenticated
using (public.safeloop_can_read_report(report_id));

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'grant all privileges on public.transcription_attempts to service_role';
    execute 'grant all privileges on public.transcript_confirmations to service_role';
  end if;
end $$;
