-- Store corpus embeddings in pgvector and index cosine nearest-neighbour search.

create extension if not exists vector;

do $$
declare
  embedding_type text;
begin
  select format_type(attribute.atttypid, attribute.atttypmod)
  into embedding_type
  from pg_attribute attribute
  where attribute.attrelid = 'public.document_chunks'::regclass
    and attribute.attname = 'embedding'
    and not attribute.attisdropped;

  if embedding_type is distinct from 'vector(1536)' then
    execute $convert$
      alter table public.document_chunks
      alter column embedding type vector(1536)
      using (
        case
          when embedding is null then null
          else ('[' || array_to_string(embedding, ',') || ']')::vector(1536)
        end
      )
    $convert$;
  end if;
end $$;

create index if not exists document_chunks_embedding_cosine_ivfflat
  on public.document_chunks
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100)
  where embedding is not null;

analyze public.document_chunks;
