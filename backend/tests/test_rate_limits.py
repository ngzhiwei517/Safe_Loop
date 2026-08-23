"""Verify endpoint limit wiring and stable 429 contracts without a database."""

from __future__ import annotations

import asyncio
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
import pytest

from app.api import documents as documents_api
from app.api import rate_limits as rate_limits_api
from app.api import reports as reports_api
from app.api.reports import CreateReportRequest
from app.domain.enums import ActorType, Role
from app.services.rate_limit_service import RateLimitExceeded
from app.services.report_service import Actor

REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")


def test_rate_limit_maps_retry_delay_to_machine_coded_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refuse(**_: object) -> None:
        raise RateLimitExceeded("report_submission", 17)

    monkeypatch.setattr(rate_limits_api, "consume_rate_limit", refuse)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            rate_limits_api.enforce_rate_limit(
                scope="report_submission",
                subject=str(REPORTER_ID),
                limit=10,
                error_code="report_rate_limited",
            )
        )
    assert error.value.status_code == 429
    assert error.value.detail["code"] == "report_rate_limited"
    assert error.value.headers == {"Retry-After": "17"}


def test_report_creation_consumes_the_report_submission_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, object] = {}

    async def enforce(**values: object) -> None:
        received.update(values)

    async def create(*_: object, **__: object) -> UUID:
        return REPORT_ID

    monkeypatch.setattr(reports_api, "enforce_rate_limit", enforce)
    monkeypatch.setattr(reports_api, "create_report", create)
    result = asyncio.run(
        reports_api.post_report(
            CreateReportRequest(description_original="Loose guardrail"),
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
    )
    assert result == {"id": REPORT_ID}
    assert received["scope"] == "report_submission"
    assert received["subject"] == str(REPORTER_ID)
    assert received["error_code"] == "report_rate_limited"


def test_document_upload_consumes_the_document_limit_before_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def enforce(**values: object) -> None:
        calls.append(str(values["scope"]))

    async def ingest(*_: object, **__: object) -> dict[str, object]:
        calls.append("ingest")
        return {"id": "document-1"}

    monkeypatch.setattr(documents_api, "enforce_rate_limit", enforce)
    monkeypatch.setattr(documents_api, "ingest_document", ingest)
    upload = UploadFile(
        BytesIO(b"%PDF-test"),
        filename="procedure.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    result = asyncio.run(
        documents_api.post_document(
            title="Procedure",
            doc_ref="PROC-1",
            revision="1",
            file=upload,
            effective_from=None,
            actor=Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
        )
    )
    assert result["id"] == "document-1"
    assert calls == ["document_upload", "ingest"]
