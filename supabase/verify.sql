-- Run with psql. Every row is PASS/FAIL; the transaction leaves no test data behind.
begin;

create temporary table verify_results (name text primary key, passed boolean not null);
create temporary table verify_report (id uuid not null);

do $$
declare
  bucket_ok boolean := false;
begin
  if to_regclass('storage.buckets') is not null then
    execute $check$
      select public is false
        and file_size_limit = 10485760
        and allowed_mime_types @> array['image/jpeg', 'image/png', 'image/webp']::text[]
        and array['image/jpeg', 'image/png', 'image/webp']::text[] @> allowed_mime_types
      from storage.buckets where id = 'report-media'
    $check$ into bucket_ok;
  end if;
  insert into verify_results values ('report_media_private_bucket', coalesce(bucket_ok, false));
end $$;

do $$
declare
  bucket_ok boolean := false;
begin
  if to_regclass('storage.buckets') is not null then
    execute $check$
      select public is false
        and file_size_limit = 26214400
        and allowed_mime_types @> array['audio/webm', 'audio/mp4', 'audio/mpeg']::text[]
        and array['audio/webm', 'audio/mp4', 'audio/mpeg']::text[] @> allowed_mime_types
      from storage.buckets where id = 'report-audio'
    $check$ into bucket_ok;
  end if;
  insert into verify_results values ('report_audio_private_bucket', coalesce(bucket_ok, false));
end $$;

insert into reports (reporter_id, description_original)
values ('00000000-0000-0000-0000-000000000001', 'verification fixture');
insert into verify_report select id from reports order by created_at desc limit 1;

insert into verify_results values
  ('report_human_ref', (select human_ref like 'SL-%' from reports where id = (select id from verify_report)));

do $$
begin
  perform set_config('safeloop.actor_type', 'ai', true);
  update reports set status = 'verified_closed' where id = (select id from verify_report);
  insert into verify_results values ('ai_closure_guard', false);
exception when insufficient_privilege then
  insert into verify_results values ('ai_closure_guard', true);
end $$;

insert into report_media (
  report_id, storage_path, mime_type, phase, retention_until
)
values (
  (select id from verify_report),
  'verify/report/audio.webm',
  'audio/webm',
  'original',
  now() + interval '90 days'
);
insert into transcripts (
  media_id, report_id, provider, model, hint_locale, detected_locale, text_raw, duration_ms,
  provider_ref, latency_ms
)
select id, report_id, 'stub', 'stub-transcription', 'en-SG', 'en-SG', 'verification transcript', 30000,
       'stub-asr-verification', 12
from report_media
where report_id = (select id from verify_report)
  and mime_type = 'audio/webm';
insert into verify_results values (
  'transcript_provider_metadata',
  exists (
    select 1 from transcripts
    where media_id in (
      select id from report_media where report_id = (select id from verify_report)
    )
      and provider_ref = 'stub-asr-verification'
      and latency_ms = 12
  )
);
insert into transcription_attempts (
  media_id, report_id, transcript_id, provider, model, hint_locale,
  detected_locale, confidence, usable, latency_ms
)
select media.id, media.report_id, transcript.id, 'stub', 'stub-transcription',
       'en-SG', 'en-SG', 0.9, true, 12
from report_media media
join transcripts transcript on transcript.media_id = media.id
where media.report_id = (select id from verify_report)
limit 1;
insert into transcript_confirmations (
  transcript_id, report_id, context, context_id, confirmed_text, input_mode
)
select transcript.id, media.report_id, 'report_description', media.report_id,
       transcript.text_raw, 'voice'
from report_media media
join transcripts transcript on transcript.media_id = media.id
where media.report_id = (select id from verify_report)
limit 1;
do $$
begin
  update transcription_attempts set usable = false
  where report_id = (select id from verify_report);
  insert into verify_results values ('voice_telemetry_append_only', false);
exception when insufficient_privilege then
  insert into verify_results values ('voice_telemetry_append_only', true);
end $$;
do $$
begin
  update transcripts set text_raw = 'changed'
  where media_id in (
    select id from report_media where report_id = (select id from verify_report)
  );
  insert into verify_results values ('transcripts_append_only', false);
exception when insufficient_privilege then
  insert into verify_results values ('transcripts_append_only', true);
end $$;
select set_config('safeloop.actor_type', 'human', true);

insert into ai_drafts (report_id, version, provider, provider_ref, raw_json, observed_facts, assumptions, missing_information)
values ((select id from verify_report), 1, 'stub', 'verify', '{}', '["fact"]', '[]', '[]');
do $$
begin
  update ai_drafts set provider_ref = 'changed' where report_id = (select id from verify_report);
  insert into verify_results values ('ai_drafts_append_only', false);
exception when insufficient_privilege then
  insert into verify_results values ('ai_drafts_append_only', true);
end $$;

insert into report_assignments (report_id, assignee_id, case_role, due_at)
values ((select id from verify_report), '00000000-0000-0000-0000-000000000004', 'responsible', now());
insert into corrective_actions (report_id, assignment_id, action_text, due_at)
select (select id from verify_report), id, 'verify fixture action', now() from report_assignments
where report_id = (select id from verify_report);
insert into verifications (report_id, corrective_action_id, reviewer_id, passed, notes)
select (select id from verify_report), id, '00000000-0000-0000-0000-000000000003', true, 'pass'
from corrective_actions where report_id = (select id from verify_report);
do $$
begin
  update verifications set notes = 'changed' where report_id = (select id from verify_report);
  insert into verify_results values ('verifications_append_only', false);
exception when insufficient_privilege then
  insert into verify_results values ('verifications_append_only', true);
end $$;

do $$
begin
  insert into briefings (report_id, version, body)
  values ((select id from verify_report), 1, '{"zh-CN":"没有英文"}');
  insert into verify_results values ('briefing_requires_en', false);
exception when check_violation then
  insert into verify_results values ('briefing_requires_en', true);
end $$;

select name, case when passed then 'PASS' else 'FAIL' end as result
from verify_results order by name;
rollback;
