"""Own corpus revisions so approval and chunk replacement cannot drift apart."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
import hashlib
from pathlib import Path
from typing import cast
from urllib.parse import quote
from uuid import UUID
from zipfile import BadZipFile, ZipFile
from io import BytesIO

import asyncpg
import httpx

from app.ai.provider import AIProvider
from app.config import get_settings
from app.db import connection
from app.domain.enums import ActorType, Role
from app.rag.chunker import DOCX_MIME_TYPE, PDF_MIME_TYPE, ChunkingError, chunk_document
from app.rag.embeddings import embed_texts_batched, vector_literal
from app.services.report_service import Actor

DocumentStorageUploader = Callable[[str, bytes, str], Awaitable[None]]
_CORPUS_ROLES = frozenset({Role.REVIEWER, Role.ADMIN})
_BROWSER_FALLBACK_MIME_TYPES = frozenset({"", "application/octet-stream"})


class DocumentError(Exception):
    """Carry a stable API code without moving readable copy into the backend."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _assert_corpus_actor(actor: Actor) -> UUID:
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.profile_id is None
        or actor.role not in _CORPUS_ROLES
    ):
        raise DocumentError("document_actor_forbidden", "corpus access requires reviewer or admin")
    return actor.profile_id


def _required_text(value: str, code: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DocumentError(code, "required document metadata is blank")
    return cleaned


def _is_docx(content: bytes) -> bool:
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = frozenset(archive.namelist())
    except (BadZipFile, OSError):
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def detect_document_type(filename: str, claimed_mime_type: str, content: bytes) -> str:
    """Use file structure rather than trusting browser-controlled MIME metadata."""
    suffix = Path(filename).suffix.lower()
    if content.startswith(b"%PDF-"):
        detected = PDF_MIME_TYPE
        expected_suffix = ".pdf"
    elif _is_docx(content):
        detected = DOCX_MIME_TYPE
        expected_suffix = ".docx"
    else:
        raise DocumentError("document_type_not_allowed", "source is not a valid PDF or DOCX")
    if suffix != expected_suffix:
        raise DocumentError("document_filename_invalid", "filename extension does not match source")
    claimed = claimed_mime_type.strip().lower()
    if claimed not in _BROWSER_FALLBACK_MIME_TYPES and claimed != detected:
        raise DocumentError("document_type_mismatch", "browser MIME type does not match source")
    return detected


def _storage_path(doc_ref: str, revision: str, mime_type: str) -> str:
    identity = hashlib.sha256(f"{doc_ref}\0{revision}".encode()).hexdigest()
    suffix = "pdf" if mime_type == PDF_MIME_TYPE else "docx"
    return f"{identity[:32]}/source.{suffix}"


async def upload_document_source(
    storage_path: str,
    content: bytes,
    mime_type: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Put one private object through the server-only Storage credential."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise DocumentError("document_storage_not_configured", "document Storage is not configured")
    endpoint = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{quote(settings.documents_bucket, safe='')}/{quote(storage_path, safe='/')}"
    )
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": mime_type,
        "x-upsert": "true",
    }
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=30.0)
    try:
        response = await active_client.post(endpoint, headers=headers, content=content)
    except httpx.HTTPError as error:
        raise DocumentError("document_storage_failed", "document Storage upload failed") from error
    finally:
        if owns_client:
            await active_client.aclose()
    if response.status_code >= 400:
        raise DocumentError("document_storage_failed", "document Storage rejected the upload")


async def ingest_document(
    actor: Actor,
    *,
    title: str,
    doc_ref: str,
    revision: str,
    effective_from: datetime | None,
    filename: str,
    claimed_mime_type: str,
    content: bytes,
    storage_uploader: DocumentStorageUploader | None = None,
    embedding_provider: AIProvider | None = None,
) -> asyncpg.Record:
    """Extract first, then atomically replace metadata and chunks for one revision."""
    profile_id = _assert_corpus_actor(actor)
    clean_title = _required_text(title, "document_title_required")
    clean_ref = _required_text(doc_ref, "document_ref_required")
    clean_revision = _required_text(revision, "document_revision_required")
    settings = get_settings()
    if not content:
        raise DocumentError("document_file_required", "document source is empty")
    if len(content) > settings.documents_max_bytes:
        raise DocumentError("document_too_large", "document source exceeds the configured byte limit")
    mime_type = detect_document_type(filename, claimed_mime_type, content)
    try:
        chunks = chunk_document(content, mime_type)
    except ChunkingError as error:
        raise DocumentError(error.code, error.message) from error
    embeddings = await embed_texts_batched(
        [chunk.content for chunk in chunks],
        provider=embedding_provider,
    )
    storage_path = _storage_path(clean_ref, clean_revision, mime_type)
    active_uploader = storage_uploader or upload_document_source
    await active_uploader(storage_path, content, mime_type)

    async with connection() as conn:
        async with conn.transaction():
            document = await conn.fetchrow(
                """
                insert into documents (
                  title, doc_ref, revision, effective_from, storage_path,
                  mime_type, uploaded_by
                )
                values ($1, $2, $3, $4, $5, $6, $7)
                on conflict (doc_ref, revision) do update set
                  title = excluded.title,
                  effective_from = excluded.effective_from,
                  storage_path = excluded.storage_path,
                  mime_type = excluded.mime_type,
                  uploaded_by = excluded.uploaded_by
                returning *
                """,
                clean_title,
                clean_ref,
                clean_revision,
                effective_from,
                storage_path,
                mime_type,
                profile_id,
            )
            if document is None:
                raise RuntimeError("database did not return ingested document")
            document_id = cast(UUID, document["id"])
            await conn.execute("delete from document_chunks where document_id = $1", document_id)
            await conn.executemany(
                """
                insert into document_chunks (
                  document_id, chunk_index, section, page, content, embedding
                )
                values ($1, $2, $3, $4, $5, $6::vector(1536))
                """,
                [
                    (
                        document_id,
                        index,
                        chunk.section,
                        chunk.page,
                        chunk.content,
                        vector_literal(embeddings[index]),
                    )
                    for index, chunk in enumerate(chunks)
                ],
            )
            result = await conn.fetchrow(
                """
                select d.*,
                       case
                         when d.is_approved then 'approved'
                         when d.retired_at is not null then 'retired'
                         else 'pending'
                       end as approval_state,
                       $2::integer as chunk_count,
                       0::bigint as cited_by_drafts
                from documents d where d.id = $1
                """,
                document_id,
                len(chunks),
            )
    if result is None:
        raise RuntimeError("database did not return corpus document")
    return result


async def list_documents(actor: Actor) -> list[asyncpg.Record]:
    """Show every revision and count immutable drafts that cite that exact row."""
    _assert_corpus_actor(actor)
    async with connection() as conn:
        rows = await conn.fetch(
            """
            select d.*,
                   case
                     when d.is_approved then 'approved'
                     when d.retired_at is not null then 'retired'
                     else 'pending'
                   end as approval_state,
                   (select count(*) from document_chunks dc where dc.document_id = d.id) as chunk_count,
                   (
                     select count(*)
                     from ai_drafts ad
                     where exists (
                       select 1
                       from jsonb_array_elements(
                         case when jsonb_typeof(ad.citations) = 'array'
                           then ad.citations else '[]'::jsonb end
                       ) citation
                       where citation->>'document_id' = d.id::text
                     )
                   ) as cited_by_drafts
            from documents d
            order by d.doc_ref, d.created_at desc, d.revision desc
            """
        )
    return list(rows)


async def approve_document(document_id: UUID, actor: Actor) -> asyncpg.Record:
    """Approve exactly one revision without changing any sibling revision."""
    profile_id = _assert_corpus_actor(actor)
    async with connection() as conn:
        document = await conn.fetchrow(
            """
            update documents
            set is_approved = true,
                approved_by = $2,
                approved_at = now(),
                retired_by = null,
                retired_at = null
            where id = $1
            returning *, 'approved'::text as approval_state
            """,
            document_id,
            profile_id,
        )
    if document is None:
        raise DocumentError("document_not_found", "document revision does not exist")
    return document


async def retire_document(document_id: UUID, actor: Actor) -> asyncpg.Record:
    """Withdraw exactly one revision while preserving its approval history fields."""
    profile_id = _assert_corpus_actor(actor)
    async with connection() as conn:
        document = await conn.fetchrow(
            """
            update documents
            set is_approved = false,
                retired_by = $2,
                retired_at = now()
            where id = $1
            returning *, 'retired'::text as approval_state
            """,
            document_id,
            profile_id,
        )
    if document is None:
        raise DocumentError("document_not_found", "document revision does not exist")
    return document
