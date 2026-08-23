-- Preserve each verification cycle and keep closure timestamps immutable.

alter table verifications
  add column if not exists new_due_at timestamptz;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'verification_failure_needs_due'
      and conrelid = 'verifications'::regclass
  ) then
    alter table verifications
      add constraint verification_failure_needs_due
      check (passed or new_due_at is not null) not valid;
  end if;
end $$;

create index if not exists verifications_report_created
  on verifications (report_id, created_at, id);

create or replace function reports_closed_at_once() returns trigger
language plpgsql as $$
begin
  if old.closed_at is not null and new.closed_at is distinct from old.closed_at then
    raise exception 'reports.closed_at is immutable once set' using errcode = '42501';
  end if;
  if old.closed_at is null
     and new.closed_at is not null
     and new.status <> 'verified_closed'::report_status then
    raise exception 'reports.closed_at requires verified closure' using errcode = '42501';
  end if;
  return new;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_trigger
    where tgname = 'reports_closed_at_once'
      and tgrelid = 'reports'::regclass
      and not tgisinternal
  ) then
    create trigger reports_closed_at_once
      before update of closed_at on reports
      for each row execute function reports_closed_at_once();
  end if;
end $$;
