-- Enforce the application role matrix at PostgreSQL's authenticated boundary.
-- The backend's service connection remains the only mutation path unless a
-- narrowly scoped write policy is declared below.

create or replace function public.safeloop_current_role()
returns public.role
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select profile.role
  from public.profiles as profile
  where profile.id = auth.uid()
$$;

create or replace function public.safeloop_is_reviewer_or_admin()
returns boolean
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select coalesce(
    public.safeloop_current_role() in (
      'reviewer'::public.role,
      'admin'::public.role
    ),
    false
  )
$$;

create or replace function public.safeloop_owns_report(target_report_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select exists (
    select 1
    from public.reports as report
    where report.id = target_report_id
      and report.reporter_id = auth.uid()
  )
$$;

create or replace function public.safeloop_has_active_assignment(target_report_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select exists (
    select 1
    from public.report_assignments as assignment
    where assignment.report_id = target_report_id
      and assignment.assignee_id = auth.uid()
      and assignment.active
  )
$$;

create or replace function public.safeloop_can_read_report(target_report_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select
    public.safeloop_is_reviewer_or_admin()
    or (
      public.safeloop_current_role() = 'reporter'::public.role
      and public.safeloop_owns_report(target_report_id)
    )
    or (
      public.safeloop_current_role() = 'responsible'::public.role
      and public.safeloop_has_active_assignment(target_report_id)
    )
$$;

create or replace function public.safeloop_can_read_briefing(target_briefing_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select
    public.safeloop_is_reviewer_or_admin()
    or exists (
      select 1
      from public.briefings as briefing
      where briefing.id = target_briefing_id
        and briefing.status = 'published'::public.briefing_status
    )
$$;

create or replace function public.safeloop_can_manage_evidence_upload(
  target_report_id uuid,
  target_storage_path text
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select
    public.safeloop_current_role() = 'responsible'::public.role
    and exists (
      select 1
      from public.report_assignments as assignment
      join public.corrective_actions as action
        on action.assignment_id = assignment.id
       and action.report_id = assignment.report_id
      join public.reports as report on report.id = assignment.report_id
      where assignment.report_id = target_report_id
        and assignment.assignee_id = auth.uid()
        and assignment.active
        and action.status = 'assigned'::public.action_status
        and report.status = 'action_assigned'::public.report_status
        and not exists (
          select 1
          from public.report_media as media
          where media.storage_path = target_storage_path
        )
    )
$$;

revoke all on function public.safeloop_current_role() from public, anon;
revoke all on function public.safeloop_is_reviewer_or_admin() from public, anon;
revoke all on function public.safeloop_owns_report(uuid) from public, anon;
revoke all on function public.safeloop_has_active_assignment(uuid) from public, anon;
revoke all on function public.safeloop_can_read_report(uuid) from public, anon;
revoke all on function public.safeloop_can_read_briefing(uuid) from public, anon;
revoke all on function public.safeloop_can_manage_evidence_upload(uuid, text) from public, anon;

grant execute on function public.safeloop_current_role() to authenticated;
grant execute on function public.safeloop_is_reviewer_or_admin() to authenticated;
grant execute on function public.safeloop_owns_report(uuid) to authenticated;
grant execute on function public.safeloop_has_active_assignment(uuid) to authenticated;
grant execute on function public.safeloop_can_read_report(uuid) to authenticated;
grant execute on function public.safeloop_can_read_briefing(uuid) to authenticated;
grant execute on function public.safeloop_can_manage_evidence_upload(uuid, text) to authenticated;

alter table public.profiles enable row level security;
alter table public.reports enable row level security;
alter table public.report_media enable row level security;
alter table public.clarifications enable row level security;
alter table public.ai_drafts enable row level security;
alter table public.review_decisions enable row level security;
alter table public.report_assignments enable row level security;
alter table public.corrective_actions enable row level security;
alter table public.verifications enable row level security;
alter table public.documents enable row level security;
alter table public.document_chunks enable row level security;
alter table public.briefings enable row level security;
alter table public.quiz_questions enable row level security;
alter table public.quiz_responses enable row level security;
alter table public.notifications enable row level security;
alter table public.alerts enable row level security;
alter table public.audit_log enable row level security;
alter table public.closure_receipts enable row level security;
alter table public.quiz_rate_limits enable row level security;

revoke all privileges on table
  public.profiles,
  public.reports,
  public.report_media,
  public.clarifications,
  public.ai_drafts,
  public.review_decisions,
  public.report_assignments,
  public.corrective_actions,
  public.verifications,
  public.documents,
  public.document_chunks,
  public.briefings,
  public.quiz_questions,
  public.quiz_responses,
  public.notifications,
  public.alerts,
  public.audit_log,
  public.closure_receipts,
  public.quiz_rate_limits
from anon, authenticated;

revoke all privileges on sequence public.report_human_ref_seq from anon, authenticated;

grant select on table public.profiles to authenticated;
grant update (preferred_lang) on table public.profiles to authenticated;

-- Authenticated users can query report rows allowed by RLS, but the identity
-- column is available only through reports_visible, where it can be masked.
grant select (
  id,
  human_ref,
  status,
  urgency,
  lang_original,
  input_mode,
  description_original,
  description_en,
  location_text,
  activity,
  level_or_zone,
  grid_ref,
  is_confidential,
  submitted_at,
  closed_at,
  created_at,
  updated_at,
  clarify_rounds,
  missing_information
) on public.reports to authenticated;

grant select on table
  public.report_media,
  public.clarifications,
  public.ai_drafts,
  public.review_decisions,
  public.report_assignments,
  public.corrective_actions,
  public.verifications,
  public.audit_log,
  public.closure_receipts
to authenticated;

grant select, insert, update, delete on table
  public.documents,
  public.document_chunks,
  public.briefings,
  public.quiz_questions
to authenticated;

grant select on table public.quiz_responses to authenticated;
grant select on table public.notifications to authenticated;
grant update (read_at) on table public.notifications to authenticated;
grant select on table public.alerts to authenticated;
grant insert (
  report_id,
  raised_by,
  location_text
) on public.alerts to authenticated;
grant update (
  acknowledged_by,
  acknowledged_at,
  resolution_note
) on public.alerts to authenticated;

drop policy if exists profiles_select_self on public.profiles;
drop policy if exists profiles_update_preferred_lang_self on public.profiles;
drop policy if exists profiles_select_visible on public.profiles;
drop policy if exists profiles_update_own_language on public.profiles;

create policy profiles_select_visible
on public.profiles for select to authenticated
using (
  id = (select auth.uid())
  or public.safeloop_is_reviewer_or_admin()
);

create policy profiles_update_own_language
on public.profiles for update to authenticated
using (id = (select auth.uid()))
with check (id = (select auth.uid()));

drop policy if exists reports_select_visible on public.reports;
create policy reports_select_visible
on public.reports for select to authenticated
using (public.safeloop_can_read_report(id));

drop policy if exists report_media_select_visible_report on public.report_media;
create policy report_media_select_visible_report
on public.report_media for select to authenticated
using (public.safeloop_can_read_report(report_id));

drop policy if exists clarifications_select_visible_report on public.clarifications;
create policy clarifications_select_visible_report
on public.clarifications for select to authenticated
using (public.safeloop_can_read_report(report_id));

drop policy if exists ai_drafts_select_visible_report on public.ai_drafts;
create policy ai_drafts_select_visible_report
on public.ai_drafts for select to authenticated
using (public.safeloop_can_read_report(report_id));

drop policy if exists review_decisions_select_visible_report on public.review_decisions;
create policy review_decisions_select_visible_report
on public.review_decisions for select to authenticated
using (public.safeloop_can_read_report(report_id));

drop policy if exists report_assignments_select_visible_report on public.report_assignments;
create policy report_assignments_select_visible_report
on public.report_assignments for select to authenticated
using (public.safeloop_can_read_report(report_id));

drop policy if exists corrective_actions_select_visible_report on public.corrective_actions;
create policy corrective_actions_select_visible_report
on public.corrective_actions for select to authenticated
using (public.safeloop_can_read_report(report_id));

drop policy if exists verifications_select_visible_report on public.verifications;
create policy verifications_select_visible_report
on public.verifications for select to authenticated
using (public.safeloop_can_read_report(report_id));

drop policy if exists audit_log_select_visible_report on public.audit_log;
create policy audit_log_select_visible_report
on public.audit_log for select to authenticated
using (
  (report_id is not null and public.safeloop_can_read_report(report_id))
  or (report_id is null and public.safeloop_is_reviewer_or_admin())
);

drop policy if exists closure_receipts_select_visible on public.closure_receipts;
create policy closure_receipts_select_visible
on public.closure_receipts for select to authenticated
using (
  reporter_id = (select auth.uid())
  or public.safeloop_is_reviewer_or_admin()
);

drop policy if exists documents_select_authenticated on public.documents;
drop policy if exists documents_write_reviewers on public.documents;
create policy documents_select_authenticated
on public.documents for select to authenticated
using (true);
create policy documents_write_reviewers
on public.documents for all to authenticated
using (public.safeloop_is_reviewer_or_admin())
with check (public.safeloop_is_reviewer_or_admin());

drop policy if exists document_chunks_select_authenticated on public.document_chunks;
drop policy if exists document_chunks_write_reviewers on public.document_chunks;
create policy document_chunks_select_authenticated
on public.document_chunks for select to authenticated
using (true);
create policy document_chunks_write_reviewers
on public.document_chunks for all to authenticated
using (public.safeloop_is_reviewer_or_admin())
with check (public.safeloop_is_reviewer_or_admin());

drop policy if exists briefings_select_visible on public.briefings;
drop policy if exists briefings_write_reviewers on public.briefings;
create policy briefings_select_visible
on public.briefings for select to authenticated
using (
  status = 'published'::public.briefing_status
  or public.safeloop_is_reviewer_or_admin()
);
create policy briefings_write_reviewers
on public.briefings for all to authenticated
using (public.safeloop_is_reviewer_or_admin())
with check (public.safeloop_is_reviewer_or_admin());

drop policy if exists quiz_questions_select_visible on public.quiz_questions;
drop policy if exists quiz_questions_write_reviewers on public.quiz_questions;
create policy quiz_questions_select_visible
on public.quiz_questions for select to authenticated
using (public.safeloop_can_read_briefing(briefing_id));
create policy quiz_questions_write_reviewers
on public.quiz_questions for all to authenticated
using (public.safeloop_is_reviewer_or_admin())
with check (public.safeloop_is_reviewer_or_admin());

drop policy if exists quiz_responses_select_own_or_reviewer on public.quiz_responses;
create policy quiz_responses_select_own_or_reviewer
on public.quiz_responses for select to authenticated
using (
  respondent_id = (select auth.uid())
  or public.safeloop_is_reviewer_or_admin()
);

drop policy if exists notifications_select_recipient on public.notifications;
drop policy if exists notifications_update_recipient on public.notifications;
create policy notifications_select_recipient
on public.notifications for select to authenticated
using (recipient_id = (select auth.uid()));
create policy notifications_update_recipient
on public.notifications for update to authenticated
using (recipient_id = (select auth.uid()))
with check (recipient_id = (select auth.uid()));

drop policy if exists alerts_select_visible on public.alerts;
drop policy if exists alerts_insert_own_report on public.alerts;
drop policy if exists alerts_update_reviewers on public.alerts;
create policy alerts_select_visible
on public.alerts for select to authenticated
using (
  raised_by = (select auth.uid())
  or public.safeloop_is_reviewer_or_admin()
);
create policy alerts_insert_own_report
on public.alerts for insert to authenticated
with check (
  public.safeloop_current_role() = 'reporter'::public.role
  and raised_by = (select auth.uid())
  and public.safeloop_owns_report(report_id)
);
create policy alerts_update_reviewers
on public.alerts for update to authenticated
using (public.safeloop_is_reviewer_or_admin())
with check (public.safeloop_is_reviewer_or_admin());

-- RLS filters rows; it cannot conditionally redact one column. This view is
-- therefore the authenticated report surface whenever reporter_id is needed.
-- It runs as its owner but repeats the row policy explicitly before masking.
create or replace view public.reports_visible
with (security_barrier = true)
as
select
  report.id,
  report.human_ref,
  case
    when public.safeloop_is_reviewer_or_admin()
      or report.reporter_id = auth.uid()
      or not report.is_confidential
    then report.reporter_id
    else null
  end as reporter_id,
  report.status,
  report.urgency,
  report.lang_original,
  report.input_mode,
  report.description_original,
  report.description_en,
  report.location_text,
  report.activity,
  report.level_or_zone,
  report.grid_ref,
  report.is_confidential,
  report.submitted_at,
  report.closed_at,
  report.created_at,
  report.updated_at,
  report.clarify_rounds,
  report.missing_information
from public.reports as report
where public.safeloop_can_read_report(report.id);

revoke all privileges on table public.reports_visible from public, anon, authenticated;
grant select on table public.reports_visible to authenticated;

-- Existing Storage policies queried protected columns directly. Replace those
-- subqueries with the audited security-definer predicates above so direct
-- mobile uploads keep working without exposing report identity columns.
do $$
begin
  if to_regclass('storage.objects') is null then
    raise notice 'Supabase Storage schema unavailable; storage RLS was not refreshed';
    return;
  end if;

  execute 'drop policy if exists report_media_insert_own_report on storage.objects';
  execute 'drop policy if exists report_media_select_own_report on storage.objects';
  execute 'drop policy if exists report_media_delete_own_unregistered_upload on storage.objects';
  execute 'drop policy if exists report_media_insert_responsible_evidence on storage.objects';
  execute 'drop policy if exists report_media_select_responsible_evidence on storage.objects';
  execute 'drop policy if exists report_media_delete_responsible_upload on storage.objects';

  execute $policy$
    create policy report_media_insert_own_report
    on storage.objects for insert to authenticated
    with check (
      bucket_id = 'report-media'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_owns_report(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_media_select_own_report
    on storage.objects for select to authenticated
    using (
      bucket_id = 'report-media'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_owns_report(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_media_delete_own_unregistered_upload
    on storage.objects for delete to authenticated
    using (
      bucket_id = 'report-media'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_owns_report(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_media_insert_responsible_evidence
    on storage.objects for insert to authenticated
    with check (
      bucket_id = 'report-media'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_can_manage_evidence_upload(
        nullif((storage.foldername(name))[2], '')::uuid,
        name
      )
    )
  $policy$;

  execute $policy$
    create policy report_media_select_responsible_evidence
    on storage.objects for select to authenticated
    using (
      bucket_id = 'report-media'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_has_active_assignment(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_media_delete_responsible_upload
    on storage.objects for delete to authenticated
    using (
      bucket_id = 'report-media'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_can_manage_evidence_upload(
        nullif((storage.foldername(name))[2], '')::uuid,
        name
      )
    )
  $policy$;
end
$$;
