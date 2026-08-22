-- Persist the durable boundary between short-lived graph runs.

alter table public.reports
  add column if not exists clarify_rounds smallint not null default 0;

alter table public.reports
  add column if not exists missing_information jsonb not null default '[]'::jsonb;

alter table public.clarifications
  add column if not exists gap text;

update public.clarifications
set gap = 'legacy'
where gap is null;

alter table public.clarifications
  alter column gap set not null;

do $$
begin
  alter table public.reports
    add constraint reports_clarify_rounds_cap
    check (clarify_rounds between 0 and 2);
exception when duplicate_object then null;
end $$;

do $$
begin
  alter table public.reports
    add constraint reports_missing_information_array
    check (jsonb_typeof(missing_information) = 'array');
exception when duplicate_object then null;
end $$;

do $$
begin
  alter table public.clarifications
    add constraint clarifications_round_cap
    check (round between 1 and 2);
exception when duplicate_object then null;
end $$;

do $$
begin
  alter table public.clarifications
    add constraint clarifications_gap_nonempty
    check (btrim(gap) <> '');
exception when duplicate_object then null;
end $$;

create index if not exists clarifications_report_round_idx
  on public.clarifications (report_id, round, created_at, id);
