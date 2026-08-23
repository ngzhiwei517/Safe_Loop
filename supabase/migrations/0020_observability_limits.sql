-- Share abuse-control counters across API processes without retaining raw identities.

create table if not exists public.request_rate_limits (
  scope text not null check (btrim(scope) <> ''),
  subject_hash text not null check (subject_hash ~ '^[0-9a-f]{64}$'),
  window_started_at timestamptz not null,
  request_count integer not null check (request_count > 0),
  primary key (scope, subject_hash, window_started_at)
);

alter table public.request_rate_limits enable row level security;
revoke all privileges on table public.request_rate_limits from anon, authenticated;

create index if not exists request_rate_limits_window_cleanup
  on public.request_rate_limits (window_started_at);
