-- Deliver active lessons publicly while keeping anonymous quiz traffic bounded.

create table if not exists public.quiz_rate_limits (
  ip_hash text not null,
  window_started_at timestamptz not null,
  request_count integer not null check (request_count > 0),
  primary key (ip_hash, window_started_at)
);

revoke all privileges on table public.quiz_rate_limits from anon, authenticated;

create index if not exists briefings_public_token_active
  on public.briefings (qr_token, valid_from, valid_to)
  where status = 'published'::briefing_status;

create index if not exists quiz_responses_respondent_question
  on public.quiz_responses (respondent_id, question_id, created_at desc)
  where respondent_id is not null;

create index if not exists quiz_rate_limits_window_cleanup
  on public.quiz_rate_limits (window_started_at);
