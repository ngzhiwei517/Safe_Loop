-- Make document revision decisions explicit and keep source files private.

alter table public.documents
  add column if not exists mime_type text,
  add column if not exists uploaded_by uuid references public.profiles(id),
  add column if not exists approved_by uuid references public.profiles(id),
  add column if not exists approved_at timestamptz,
  add column if not exists retired_by uuid references public.profiles(id),
  add column if not exists retired_at timestamptz;

alter table public.document_chunks
  add column if not exists chunk_index integer not null default 0;

with ranked as (
  select id, row_number() over (
    partition by document_id order by created_at, id
  ) - 1 as position
  from public.document_chunks
)
update public.document_chunks as chunks
set chunk_index = ranked.position
from ranked
where chunks.id = ranked.id;

create unique index if not exists documents_storage_path_unique
  on public.documents (storage_path)
  where storage_path is not null;

create unique index if not exists document_chunks_document_position_unique
  on public.document_chunks (document_id, chunk_index);

create index if not exists documents_reference_revision
  on public.documents (doc_ref, revision);

do $$
begin
  if to_regclass('storage.buckets') is null or to_regclass('storage.objects') is null then
    raise notice 'Supabase Storage schema unavailable; documents bucket was not created';
    return;
  end if;

  execute $bucket$
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values (
      'documents',
      'documents',
      false,
      26214400,
      array[
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      ]::text[]
    )
    on conflict (id) do update set
      public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types
  $bucket$;
end $$;
