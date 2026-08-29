-- Phase 7 storage foundation: private report audio and immutable transcript audit rows.

alter table public.report_media
  add column if not exists retention_until timestamptz;

alter table public.report_media
  drop constraint if exists report_media_retention_after_creation;

alter table public.report_media
  add constraint report_media_retention_after_creation
  check (retention_until is null or retention_until > created_at);

create table if not exists public.transcripts (
  id uuid primary key default gen_random_uuid(),
  media_id uuid not null references public.report_media(id) on delete cascade,
  provider text not null,
  model text not null,
  hint_locale text,
  detected_locale text,
  text_raw text not null,
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  duration_ms integer check (duration_ms is null or duration_ms >= 0),
  created_at timestamptz not null default now()
);

create index if not exists transcripts_media_id_created_at
  on public.transcripts (media_id, created_at desc);

create or replace function public.transcripts_no_update() returns trigger
language plpgsql as $$
begin
  raise exception 'transcripts are append-only' using errcode = '42501';
end $$;

drop trigger if exists transcripts_no_update on public.transcripts;
create trigger transcripts_no_update before update on public.transcripts
for each row execute function public.transcripts_no_update();

alter table public.transcripts enable row level security;
revoke all privileges on table public.transcripts from public, anon, authenticated;
grant select on table public.transcripts to authenticated;

drop policy if exists transcripts_select_visible_report on public.transcripts;
create policy transcripts_select_visible_report
on public.transcripts for select to authenticated
using (
  exists (
    select 1
    from public.report_media as media
    where media.id = transcripts.media_id
      and public.safeloop_can_read_report(media.report_id)
  )
);

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'grant all privileges on table public.transcripts to service_role';
  end if;

  if to_regclass('storage.buckets') is null or to_regclass('storage.objects') is null then
    raise notice 'Supabase Storage schema unavailable; report-audio bucket was not created';
    return;
  end if;

  execute $bucket$
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values (
      'report-audio',
      'report-audio',
      false,
      26214400,
      array['audio/webm', 'audio/mp4', 'audio/mpeg']::text[]
    )
    on conflict (id) do update set
      public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types
  $bucket$;

  execute 'drop policy if exists report_audio_insert_own_report on storage.objects';
  execute 'drop policy if exists report_audio_select_own_report on storage.objects';
  execute 'drop policy if exists report_audio_delete_own_unregistered_upload on storage.objects';
  execute 'drop policy if exists report_audio_insert_responsible_evidence on storage.objects';
  execute 'drop policy if exists report_audio_select_responsible_evidence on storage.objects';
  execute 'drop policy if exists report_audio_delete_responsible_upload on storage.objects';

  execute $policy$
    create policy report_audio_insert_own_report
    on storage.objects for insert to authenticated
    with check (
      bucket_id = 'report-audio'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_owns_report(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_audio_select_own_report
    on storage.objects for select to authenticated
    using (
      bucket_id = 'report-audio'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_owns_report(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_audio_delete_own_unregistered_upload
    on storage.objects for delete to authenticated
    using (
      bucket_id = 'report-audio'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_owns_report(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_audio_insert_responsible_evidence
    on storage.objects for insert to authenticated
    with check (
      bucket_id = 'report-audio'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_can_manage_evidence_upload(
        nullif((storage.foldername(name))[2], '')::uuid,
        name
      )
    )
  $policy$;

  execute $policy$
    create policy report_audio_select_responsible_evidence
    on storage.objects for select to authenticated
    using (
      bucket_id = 'report-audio'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_has_active_assignment(
        nullif((storage.foldername(name))[2], '')::uuid
      )
    )
  $policy$;

  execute $policy$
    create policy report_audio_delete_responsible_upload
    on storage.objects for delete to authenticated
    using (
      bucket_id = 'report-audio'
      and (storage.foldername(name))[1] = auth.uid()::text
      and public.safeloop_can_manage_evidence_upload(
        nullif((storage.foldername(name))[2], '')::uuid,
        name
      )
    )
  $policy$;
end
$$;
