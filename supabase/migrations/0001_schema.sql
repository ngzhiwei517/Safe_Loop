-- SafeLoop AI's initial schema and database-level invariant guards.

create extension if not exists pgcrypto;
do $$
begin
  create extension if not exists vector;
exception when others then
  raise notice 'pgvector unavailable; using a portable embedding array';
end $$;

create type role as enum ('reporter', 'reviewer', 'responsible', 'crew', 'admin');
create type actor_type as enum ('human', 'ai', 'system');
create type report_status as enum (
  'draft', 'submitted', 'clarifying', 'ai_drafted', 'under_review', 'rejected',
  'info_requested', 'escalated', 'action_assigned', 'action_submitted',
  'verified_closed', 'lesson_drafted', 'lesson_published'
);
create type urgency as enum ('low', 'medium', 'high', 'critical');
create type review_decision as enum ('approve', 'request_info', 'escalate', 'reject');
create type action_status as enum ('assigned', 'submitted', 'verified');
create type case_role as enum ('responsible');
create type media_phase as enum ('original', 'evidence');
create type validation_status as enum ('valid', 'invalid');
create type briefing_status as enum ('draft', 'published');
create type input_mode as enum ('typed', 'voice', 'voice_edited');

create sequence report_human_ref_seq;

create table profiles (
  id uuid primary key,
  role role not null,
  preferred_lang text not null default 'en' check (preferred_lang in ('en', 'zh-CN')),
  project_id uuid,
  created_at timestamptz not null default now()
);

create table reports (
  id uuid primary key default gen_random_uuid(),
  human_ref text not null unique,
  reporter_id uuid not null references profiles(id),
  status report_status not null default 'draft',
  urgency urgency not null default 'medium',
  lang_original text not null default 'en',
  input_mode input_mode not null default 'typed',
  description_original text not null,
  description_en text,
  location_text text,
  activity text,
  level_or_zone text,
  grid_ref text,
  is_confidential boolean not null default false,
  submitted_at timestamptz,
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table report_media (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  storage_path text not null,
  mime_type text not null,
  phase media_phase not null,
  caption text,
  created_at timestamptz not null default now()
);

create table clarifications (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  round smallint not null,
  question text not null,
  answer text,
  answered_at timestamptz,
  created_at timestamptz not null default now()
);

create table ai_drafts (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  version integer not null,
  provider text not null,
  provider_ref text not null,
  raw_json jsonb not null,
  observed_facts jsonb not null,
  assumptions jsonb not null,
  missing_information jsonb not null,
  proposed_category text,
  proposed_urgency urgency,
  suggested_owner_role role,
  suggested_action text,
  confidence numeric,
  needs_escalation boolean not null default false,
  citations jsonb not null default '[]'::jsonb,
  validation validation_status,
  validation_errors jsonb not null default '[]'::jsonb,
  latency_ms integer,
  tokens_in integer,
  tokens_out integer,
  created_at timestamptz not null default now(),
  unique (report_id, version)
);

create table review_decisions (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  reviewer_id uuid not null references profiles(id),
  decision review_decision not null,
  corrections jsonb,
  correction_reason text,
  reason text,
  created_at timestamptz not null default now(),
  check (corrections is null or correction_reason is not null and btrim(correction_reason) <> '')
);

create table report_assignments (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  assignee_id uuid not null references profiles(id),
  case_role case_role not null,
  due_at timestamptz not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create unique index report_assignments_one_active
  on report_assignments (report_id, case_role) where active;

create table corrective_actions (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  assignment_id uuid not null references report_assignments(id),
  action_text text not null,
  status action_status not null default 'assigned',
  rework_count smallint not null default 0,
  due_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table verifications (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  corrective_action_id uuid not null references corrective_actions(id),
  reviewer_id uuid not null references profiles(id),
  passed boolean not null,
  checklist jsonb,
  notes text,
  reason text,
  created_at timestamptz not null default now(),
  check (passed or reason is not null and btrim(reason) <> '')
);

create table documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  doc_ref text not null,
  revision text not null,
  is_approved boolean not null default false,
  effective_from timestamptz,
  storage_path text,
  created_at timestamptz not null default now(),
  unique (doc_ref, revision)
);

create table document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  section text,
  page integer,
  content text not null,
  embedding double precision[],
  created_at timestamptz not null default now()
);

create table briefings (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  version integer not null,
  body jsonb not null check (jsonb_typeof(body->'en') = 'string' and btrim(body->>'en') <> ''),
  status briefing_status not null default 'draft',
  target_activity text,
  target_location text,
  valid_from timestamptz,
  valid_to timestamptz,
  qr_token text unique,
  approved_by uuid references profiles(id),
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (report_id, version)
);

create or replace function jsonb_options_have_en(value jsonb) returns boolean
language sql immutable as $$
  select jsonb_typeof(value) = 'array'
    and jsonb_array_length(value) > 0
    and not exists (
      select 1 from jsonb_array_elements(value) option
      where jsonb_typeof(option->'en') <> 'string' or btrim(option->>'en') = ''
    )
$$;

create table quiz_questions (
  id uuid primary key default gen_random_uuid(),
  briefing_id uuid not null references briefings(id) on delete cascade,
  position smallint not null,
  question jsonb not null check (jsonb_typeof(question->'en') = 'string' and btrim(question->>'en') <> ''),
  explanation jsonb not null check (jsonb_typeof(explanation->'en') = 'string' and btrim(explanation->>'en') <> ''),
  options jsonb not null check (jsonb_options_have_en(options)),
  correct_option smallint not null,
  created_at timestamptz not null default now(),
  unique (briefing_id, position)
);

create table quiz_responses (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null references quiz_questions(id) on delete cascade,
  respondent_id uuid references profiles(id),
  selected_option smallint not null,
  is_correct boolean not null,
  created_at timestamptz not null default now()
);

create table notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_id uuid not null references profiles(id),
  kind text not null,
  entity_type text not null,
  entity_id uuid not null,
  payload jsonb not null default '{}'::jsonb,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create table alerts (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id) on delete cascade,
  raised_by uuid not null references profiles(id),
  raised_at timestamptz not null default now(),
  location_text text,
  acknowledged_by uuid references profiles(id),
  acknowledged_at timestamptz,
  escalated_at timestamptz,
  resolution_note text,
  created_at timestamptz not null default now()
);

create table audit_log (
  id uuid primary key default gen_random_uuid(),
  report_id uuid references reports(id) on delete cascade,
  actor_type actor_type not null,
  actor_id uuid,
  event text not null,
  source report_status,
  target report_status,
  reason text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index reports_status_urgency_age on reports (status, urgency, created_at);
create index reports_reporter_id on reports (reporter_id);
create index report_media_report_id on report_media (report_id);
create index ai_drafts_report_id_created_at on ai_drafts (report_id, created_at desc);
create index audit_log_report_id_created_at on audit_log (report_id, created_at);
create index notifications_recipient_unread on notifications (recipient_id, read_at, created_at desc);
create index alerts_acknowledged_at_raised_at on alerts (acknowledged_at, raised_at);
create index document_chunks_document_id on document_chunks (document_id);

create or replace function reports_set_ref() returns trigger
language plpgsql as $$
begin
  if new.human_ref is null or new.human_ref = '' then
    new.human_ref := 'SL-' || to_char(coalesce(new.created_at, now()), 'YYYY') || '-' ||
      lpad(nextval('report_human_ref_seq')::text, 5, '0');
  end if;
  return new;
end $$;

create trigger reports_set_ref before insert on reports
for each row execute function reports_set_ref();

create or replace function reports_touch() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create trigger reports_touch before update on reports
for each row execute function reports_touch();

create or replace function ai_drafts_no_update() returns trigger
language plpgsql as $$
begin
  raise exception 'ai_drafts are append-only' using errcode = '42501';
end $$;

create trigger ai_drafts_no_update before update on ai_drafts
for each row execute function ai_drafts_no_update();

create or replace function verifications_no_update() returns trigger
language plpgsql as $$
begin
  raise exception 'verifications are append-only' using errcode = '42501';
end $$;

create trigger verifications_no_update before update on verifications
for each row execute function verifications_no_update();

create or replace function enforce_status_actor() returns trigger
language plpgsql as $$
declare
  actor text := current_setting('safeloop.actor_type', true);
begin
  if new.status in (
    'under_review', 'info_requested', 'rejected', 'escalated',
    'action_assigned', 'action_submitted', 'verified_closed', 'lesson_published'
  ) and actor = 'ai' then
    raise exception 'AI actor cannot reach this status' using errcode = '42501';
  end if;
  if new.status = 'verified_closed' and actor is distinct from 'human' then
    raise exception 'only a human actor can close a report' using errcode = '42501';
  end if;
  return new;
end $$;

create trigger enforce_status_actor before update of status on reports
for each row when (old.status is distinct from new.status)
execute function enforce_status_actor();
