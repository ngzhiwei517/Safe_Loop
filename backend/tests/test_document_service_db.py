"""Prove revision approval isolation and transactional chunk replacement in Postgres."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, Role
from app.rag.chunker import DOCX_MIME_TYPE, PDF_MIME_TYPE, chunk_document
from app.services.document_service import (
    approve_document,
    ingest_document,
    list_documents,
    retire_document,
)
from app.services.report_service import Actor

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
FIXTURES = Path(__file__).parent / "fixtures"
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
_test_loop: asyncio.AbstractEventLoop | None = None
T = TypeVar("T")


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Keep this integration module on one event loop and one shared pool."""
    global _test_loop
    assert DATABASE_URL is not None
    _test_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_test_loop)
    _test_loop.run_until_complete(init_pool(DATABASE_URL))
    yield
    _test_loop.run_until_complete(close_pool())
    _test_loop.close()
    _test_loop = None
    asyncio.set_event_loop(None)


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    assert _test_loop is not None
    return _test_loop.run_until_complete(coroutine)


def reviewer() -> Actor:
    return Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)


async def no_storage(_path: str, _content: bytes, _mime_type: str) -> None:
    return None


async def cleanup(doc_ref: str) -> None:
    async with connection() as conn:
        await conn.execute("delete from documents where doc_ref = $1", doc_ref)


def test_reingest_replaces_chunks_and_revision_approval_is_isolated() -> None:
    doc_ref = f"TEST-{uuid4()}"
    pdf = (FIXTURES / "english-procedure.pdf").read_bytes()
    docx = (FIXTURES / "zh-CN-procedure.docx").read_bytes()
    effective = datetime.now(timezone.utc)
    try:
        revision_two = run(
            ingest_document(
                reviewer(),
                title="English procedure",
                doc_ref=doc_ref,
                revision="2",
                effective_from=effective,
                filename="procedure.pdf",
                claimed_mime_type=PDF_MIME_TYPE,
                content=pdf,
                storage_uploader=no_storage,
            )
        )
        run(approve_document(revision_two["id"], reviewer()))
        revision_three = run(
            ingest_document(
                reviewer(),
                title="中文程序",
                doc_ref=doc_ref,
                revision="3",
                effective_from=effective,
                filename="procedure.docx",
                claimed_mime_type=DOCX_MIME_TYPE,
                content=docx,
                storage_uploader=no_storage,
            )
        )

        documents = run(list_documents(reviewer()))
        states = {row["revision"]: row["approval_state"] for row in documents if row["doc_ref"] == doc_ref}
        assert states == {"2": "approved", "3": "pending"}

        expected_pdf_chunks = len(chunk_document(pdf, PDF_MIME_TYPE))
        run(
            ingest_document(
                reviewer(),
                title="English replacement",
                doc_ref=doc_ref,
                revision="3",
                effective_from=effective,
                filename="replacement.pdf",
                claimed_mime_type=PDF_MIME_TYPE,
                content=pdf,
                storage_uploader=no_storage,
            )
        )

        async def chunk_count() -> int:
            async with connection() as conn:
                return int(
                    await conn.fetchval(
                        "select count(*) from document_chunks where document_id = $1",
                        revision_three["id"],
                    )
                )

        assert run(chunk_count()) == expected_pdf_chunks
        run(retire_document(revision_two["id"], reviewer()))
        final = run(list_documents(reviewer()))
        final_states = {row["revision"]: row["approval_state"] for row in final if row["doc_ref"] == doc_ref}
        assert final_states == {"2": "retired", "3": "pending"}
    finally:
        run(cleanup(doc_ref))


def test_documents_bucket_is_private_when_storage_is_available() -> None:
    async def inspect() -> tuple[bool, int | None, list[str] | None] | None:
        async with connection() as conn:
            storage_exists = await conn.fetchval("select to_regclass('storage.buckets') is not null")
            if not storage_exists:
                return None
            row = await conn.fetchrow(
                """
                select public, file_size_limit, allowed_mime_types
                from storage.buckets where id = 'documents'
                """
            )
            if row is None:
                return None
            return row["public"], row["file_size_limit"], row["allowed_mime_types"]

    bucket = run(inspect())
    if bucket is None:
        pytest.skip("Supabase Storage schema is unavailable")
    is_public, file_size_limit, mime_types = bucket
    assert is_public is False
    assert file_size_limit == 25 * 1024 * 1024
    assert mime_types is not None
    assert set(mime_types) == {PDF_MIME_TYPE, DOCX_MIME_TYPE}
