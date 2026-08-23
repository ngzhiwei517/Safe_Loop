-- Deliver one overdue reminder per local day and support operational summaries.

alter table public.notifications
  add column if not exists delivery_date date;

update public.notifications
set delivery_date = created_at::date
where kind = 'overdue' and delivery_date is null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'notifications_overdue_delivery_date'
      and conrelid = 'public.notifications'::regclass
  ) then
    alter table public.notifications
      add constraint notifications_overdue_delivery_date
      check ((kind = 'overdue') = (delivery_date is not null));
  end if;
end $$;

create unique index if not exists notifications_one_overdue_per_day
  on public.notifications (
    recipient_id, kind, entity_type, entity_id, delivery_date
  )
  where kind = 'overdue';

create index if not exists audit_log_metrics_targets
  on public.audit_log (report_id, target, created_at)
  where target in (
    'under_review'::report_status,
    'action_assigned'::report_status,
    'verified_closed'::report_status
  );

create index if not exists review_decisions_report_corrections
  on public.review_decisions (report_id)
  include (corrections);
