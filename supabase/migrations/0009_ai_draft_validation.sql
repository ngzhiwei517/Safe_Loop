-- Persist validation evidence with the immutable draft and index manual triage.

alter table public.ai_drafts
  add column if not exists escalation_reason text;

create index if not exists ai_drafts_manual_triage
  on public.ai_drafts (report_id, version desc)
  where validation = 'invalid'::validation_status;
