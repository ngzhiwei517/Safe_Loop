-- Keep learning-outcome and rolling repeat-hazard summaries index-backed.

create index if not exists quiz_responses_first_identified_attempt
  on public.quiz_responses (question_id, respondent_id, created_at, id)
  include (is_correct)
  where respondent_id is not null;

create index if not exists reports_recent_closed_location
  on public.reports (
    closed_at desc,
    (lower(regexp_replace(btrim(location_text), '\s+', ' ', 'g')))
  )
  where closed_at is not null and location_text is not null;
