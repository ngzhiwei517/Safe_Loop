-- Make the report/transcript relationship explicit while preserving raw ASR output.

alter table public.report_media
  add constraint report_media_id_report_unique unique (id, report_id);

alter table public.transcripts
  add column if not exists report_id uuid references public.reports(id) on delete cascade;

update public.transcripts as transcript
set report_id = media.report_id
from public.report_media as media
where media.id = transcript.media_id
  and transcript.report_id is null;

alter table public.transcripts
  alter column report_id set not null;

alter table public.transcripts
  add constraint transcripts_media_report_fk
  foreign key (media_id, report_id)
  references public.report_media(id, report_id)
  on delete cascade;

create index if not exists transcripts_report_id_created_at
  on public.transcripts (report_id, created_at desc);
