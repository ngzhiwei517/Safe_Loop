-- Snapshot the human-verified facts shown to a reporter after closure.

create table closure_receipts (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null unique references reports(id) on delete cascade,
  verification_id uuid not null unique references verifications(id),
  corrective_action_id uuid not null references corrective_actions(id),
  reporter_id uuid not null references profiles(id),
  reporter_locale text not null check (reporter_locale in ('en', 'zh-CN')),
  action_text text not null check (btrim(action_text) <> ''),
  verification_notes text not null check (btrim(verification_notes) <> ''),
  verified_by_id uuid not null references profiles(id),
  verified_by_name text not null check (btrim(verified_by_name) <> ''),
  before_media_id uuid references report_media(id),
  after_media_id uuid references report_media(id),
  created_at timestamptz not null default now(),
  check ((before_media_id is null) = (after_media_id is null))
);

create unique index notifications_one_report_closed_per_report
  on notifications (entity_type, entity_id)
  where kind = 'report_closed';

create or replace function closure_receipts_no_update() returns trigger
language plpgsql as $$
begin
  raise exception 'closure receipts are immutable' using errcode = '42501';
end $$;

create trigger closure_receipts_no_update
before update on closure_receipts
for each row execute function closure_receipts_no_update();
