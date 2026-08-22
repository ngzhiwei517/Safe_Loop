-- Private original-report photos uploaded directly by authenticated reporters.

create unique index if not exists report_media_storage_path_unique
  on report_media (storage_path);

do $$
begin
  if to_regclass('storage.buckets') is null or to_regclass('storage.objects') is null then
    raise notice 'Supabase Storage schema unavailable; report-media bucket was not created';
    return;
  end if;

  execute $bucket$
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values (
      'report-media',
      'report-media',
      false,
      10485760,
      array['image/jpeg', 'image/png', 'image/webp']::text[]
    )
    on conflict (id) do update set
      public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types
  $bucket$;

  begin
    execute $policy$
      create policy report_media_insert_own_report
      on storage.objects for insert to authenticated
      with check (
        bucket_id = 'report-media'
        and (storage.foldername(name))[1] = auth.uid()::text
        and exists (
          select 1 from public.reports
          where reports.id::text = (storage.foldername(name))[2]
            and reports.reporter_id = auth.uid()
        )
      )
    $policy$;
  exception when duplicate_object then
    null;
  end;

  begin
    execute $policy$
      create policy report_media_select_own_report
      on storage.objects for select to authenticated
      using (
        bucket_id = 'report-media'
        and (storage.foldername(name))[1] = auth.uid()::text
        and exists (
          select 1 from public.reports
          where reports.id::text = (storage.foldername(name))[2]
            and reports.reporter_id = auth.uid()
        )
      )
    $policy$;
  exception when duplicate_object then
    null;
  end;

  begin
    execute $policy$
      create policy report_media_delete_own_unregistered_upload
      on storage.objects for delete to authenticated
      using (
        bucket_id = 'report-media'
        and (storage.foldername(name))[1] = auth.uid()::text
        and exists (
          select 1 from public.reports
          where reports.id::text = (storage.foldername(name))[2]
            and reports.reporter_id = auth.uid()
        )
      )
    $policy$;
  exception when duplicate_object then
    null;
  end;
end $$;
