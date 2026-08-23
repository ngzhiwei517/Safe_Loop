-- Keep published lessons immutable and require complete publication metadata.

alter table public.briefings
  drop constraint if exists briefing_validity_order;
alter table public.briefings
  add constraint briefing_validity_order check (
    valid_from is null or valid_to is null or valid_to > valid_from
  );

alter table public.briefings
  drop constraint if exists briefing_publication_complete;
alter table public.briefings
  add constraint briefing_publication_complete check (
    status = 'draft'::briefing_status
    or (
      status = 'published'::briefing_status
      and qr_token is not null
      and length(qr_token) >= 22
      and approved_by is not null
      and approved_at is not null
      and valid_from is not null
      and valid_to is not null
      and (jsonb_typeof(body -> 'zh-CN') = 'string'
           and btrim(body ->> 'zh-CN') <> '') is true
    )
  );

create or replace function public.briefings_published_no_update()
returns trigger
language plpgsql
as $$
begin
  if old.status = 'published'::briefing_status then
    raise exception 'published briefings are immutable' using errcode = '55000';
  end if;
  return new;
end;
$$;

drop trigger if exists briefings_published_no_update on public.briefings;
create trigger briefings_published_no_update
before update on public.briefings
for each row execute function public.briefings_published_no_update();

create or replace function public.quiz_questions_published_no_update()
returns trigger
language plpgsql
as $$
begin
  if exists (
    select 1
    from public.briefings
    where id = old.briefing_id
      and status = 'published'::briefing_status
  ) then
    raise exception 'published briefing questions are immutable' using errcode = '55000';
  end if;
  return new;
end;
$$;

drop trigger if exists quiz_questions_published_no_update on public.quiz_questions;
create trigger quiz_questions_published_no_update
before update on public.quiz_questions
for each row execute function public.quiz_questions_published_no_update();

create index if not exists briefings_report_status_version
  on public.briefings (report_id, status, version desc);
