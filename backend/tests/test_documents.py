"""Test corpus permission, file validation, Storage transport, and API errors offline."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from app.api.documents import document_error
from app.config import get_settings
from app.domain.enums import ActorType, Role
from app.rag.chunker import DOCX_MIME_TYPE, PDF_MIME_TYPE
from app.services.document_service import (
    DocumentError,
    detect_document_type,
    list_documents,
    upload_document_source,
)
from app.services.report_service import Actor

FIXTURES = Path(__file__).parent / "fixtures"
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_detects_pdf_and_docx_from_content() -> None:
    pdf = (FIXTURES / "english-procedure.pdf").read_bytes()
    docx = (FIXTURES / "zh-CN-procedure.docx").read_bytes()

    assert detect_document_type("procedure.pdf", PDF_MIME_TYPE, pdf) == PDF_MIME_TYPE
    assert detect_document_type("procedure.docx", "application/octet-stream", docx) == DOCX_MIME_TYPE


def test_mismatched_filename_is_rejected() -> None:
    pdf = (FIXTURES / "english-procedure.pdf").read_bytes()
    with pytest.raises(DocumentError) as error:
        detect_document_type("procedure.docx", PDF_MIME_TYPE, pdf)
    assert error.value.code == "document_filename_invalid"


def test_reporter_cannot_access_corpus() -> None:
    actor = Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER)
    with pytest.raises(DocumentError) as error:
        asyncio.run(list_documents(actor))
    assert error.value.code == "document_actor_forbidden"
    assert document_error(error.value).status_code == 403


def test_private_storage_upload_uses_service_credential_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-test-key")
    get_settings.cache_clear()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"Key": "documents/path/source.pdf"})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await upload_document_source(
                "path/source.pdf",
                b"%PDF-fixture",
                PDF_MIME_TYPE,
                client=client,
            )

    try:
        asyncio.run(exercise())
    finally:
        get_settings.cache_clear()

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path.endswith("/storage/v1/object/documents/path/source.pdf")
    assert request.headers["authorization"] == "Bearer service-test-key"
    assert request.headers["x-upsert"] == "true"


def test_storage_failure_is_machine_coded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-test-key")
    get_settings.cache_clear()

    async def exercise() -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(500))
        async with httpx.AsyncClient(transport=transport) as client:
            await upload_document_source(
                "path/source.pdf",
                b"%PDF-fixture",
                PDF_MIME_TYPE,
                client=client,
            )

    try:
        with pytest.raises(DocumentError) as error:
            asyncio.run(exercise())
    finally:
        get_settings.cache_clear()
    assert error.value.code == "document_storage_failed"
    assert document_error(error.value).status_code == 502
