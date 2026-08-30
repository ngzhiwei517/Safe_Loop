-- Preserve the provider evidence returned by the Phase 7 transcription seam.

alter table public.transcripts
  add column if not exists provider_ref text,
  add column if not exists latency_ms integer;

alter table public.transcripts
  drop constraint if exists transcripts_latency_nonnegative;

alter table public.transcripts
  add constraint transcripts_latency_nonnegative
  check (latency_ms is null or latency_ms >= 0);
