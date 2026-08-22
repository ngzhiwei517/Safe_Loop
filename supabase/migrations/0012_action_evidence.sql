-- Link technician evidence to the corrective action it proves.

alter table corrective_actions
  add column if not exists completed_note text,
  add column if not exists submitted_at timestamptz;

alter table report_media
  add column if not exists corrective_action_id uuid
    references corrective_actions(id);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'report_media_action_requires_evidence'
      and conrelid = 'report_media'::regclass
  ) then
    alter table report_media
      add constraint report_media_action_requires_evidence
      check (corrective_action_id is null or phase = 'evidence'::media_phase);
  end if;
end $$;

create index if not exists report_media_corrective_action_created
  on report_media (corrective_action_id, created_at, id)
  where corrective_action_id is not null;

create index if not exists corrective_actions_open_due
  on corrective_actions (due_at, id)
  where status = 'assigned'::action_status;

create index if not exists verifications_action_failed_created
  on verifications (corrective_action_id, created_at desc, id desc)
  where not passed;

-- Supabase Storage is optional for bare-Postgres verification. When present,
-- active responsible assignees may upload and clean up their own evidence.
do $$
begin
  if to_regclass('storage.objects') is null then
    raise notice 'Supabase Storage schema unavailable; responsible evidence policies were not created';
    return;
  end if;

  begin
    execute $policy$
      create policy report_media_insert_responsible_evidence
      on storage.objects for insert to authenticated
      with check (
        bucket_id = 'report-media'
        and (storage.foldername(name))[1] = auth.uid()::text
        and exists (
          select 1
          from public.report_assignments assignment
          join public.corrective_actions action
            on action.assignment_id = assignment.id
           and action.report_id = assignment.report_id
          join public.reports report on report.id = assignment.report_id
          where assignment.report_id::text = (storage.foldername(name))[2]
            and assignment.assignee_id = auth.uid()
            and assignment.active
            and action.status = 'assigned'::public.action_status
            and report.status = 'action_assigned'::public.report_status
            and not exists (
              select 1 from public.report_media media where media.storage_path = name
            )
        )
      )
    $policy$;
  exception when duplicate_object then
    null;
  end;

  begin
    execute $policy$
      create policy report_media_select_responsible_evidence
      on storage.objects for select to authenticated
      using (
        bucket_id = 'report-media'
        and (storage.foldername(name))[1] = auth.uid()::text
        and exists (
          select 1
          from public.report_assignments assignment
          where assignment.report_id::text = (storage.foldername(name))[2]
            and assignment.assignee_id = auth.uid()
            and assignment.active
        )
      )
    $policy$;
  exception when duplicate_object then
    null;
  end;

  begin
    execute $policy$
      create policy report_media_delete_responsible_upload
      on storage.objects for delete to authenticated
      using (
        bucket_id = 'report-media'
        and (storage.foldername(name))[1] = auth.uid()::text
        and exists (
          select 1
          from public.report_assignments assignment
          join public.corrective_actions action
            on action.assignment_id = assignment.id
           and action.report_id = assignment.report_id
          join public.reports report on report.id = assignment.report_id
          where assignment.report_id::text = (storage.foldername(name))[2]
            and assignment.assignee_id = auth.uid()
            and assignment.active
            and action.status = 'assigned'::public.action_status
            and report.status = 'action_assigned'::public.report_status
            and not exists (
              select 1 from public.report_media media where media.storage_path = name
            )
        )
      )
    $policy$;
  exception when duplicate_object then
    null;
  end;
end $$;
