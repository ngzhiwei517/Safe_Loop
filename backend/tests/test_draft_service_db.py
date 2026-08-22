"""Prove versioned AI drafts append with exact provider evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
import json
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.ai.intake_graph import DraftEnvelope, DraftPayload
from app.ai.validator import CITATION_QUOTE_NOT_VERBATIM
from app.db import close_pool, connection, init_pool
from app.services.draft_service import append_draft
from app.services.report_service import create_report, get_report

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
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


def envelope(provider_ref: str, *, latency_ms: int) -> DraftEnvelope:
    payload: DraftPayload = {
        "observed_facts": ["Guardrail missing at Level 6"],
        "assumptions": [],
        "missing_information": [],
        "proposed_category": "work_at_height",
        "proposed_urgency": "high",
        "suggested_owner_role": "responsible",
        "suggested_action": None,
        "confidence": 0.9,
        "needs_escalation": False,
        "escalation_reason": None,
        "citations": [],
    }
    return {
        **payload,
        "raw": json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "provider": "stub",
        "provider_ref": provider_ref,
        "latency_ms": latency_ms,
        "tokens_in": 21,
        "tokens_out": 34,
    }


def cited_envelope(document_id: UUID, doc_ref: str, quote: str) -> DraftEnvelope:
    payload: DraftPayload = {
        "observed_facts": ["Guardrail missing at Level 6"],
        "assumptions": [],
        "missing_information": [],
        "proposed_category": "work_at_height",
        "proposed_urgency": "high",
        "suggested_owner_role": "responsible",
        "suggested_action": quote,
        "confidence": 0.9,
        "needs_escalation": False,
        "escalation_reason": None,
        "citations": [
            {
                "document_id": str(document_id),
                "doc_ref": doc_ref,
                "revision": "1",
                "section": "4.2",
                "page": 7,
                "quote": quote,
            }
        ],
    }
    return {
        **payload,
        "raw": json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "provider": "stub",
        "provider_ref": "stub-citation-test",
        "latency_ms": 3,
        "tokens_in": 10,
        "tokens_out": 12,
    }


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute("delete from reports where id = $1", report_id)


async def create_approved_source() -> tuple[UUID, str]:
    doc_ref = f"WAH-CITATION-{uuid4().hex}"
    async with connection() as conn:
        document_id = await conn.fetchval(
            """
            insert into documents (
              id, title, doc_ref, revision, is_approved, effective_from
            )
            values ($1, 'Citation test', $2, '1', true, now())
            returning id
            """,
            uuid4(),
            doc_ref,
        )
        assert isinstance(document_id, UUID)
        await conn.execute(
            """
            insert into document_chunks (
              document_id, chunk_index, section, page, content
            )
            values ($1, 0, '4.2', 7, 'Inspect the edge before work starts.')
            """,
            document_id,
        )
        return document_id, doc_ref


async def cleanup_with_source(report_id: UUID, document_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute("delete from reports where id = $1", report_id)
        await conn.execute("delete from documents where id = $1", document_id)


def test_two_runs_append_versions_one_and_two() -> None:
    report_id = run(create_report(REPORTER_ID, "Guardrail missing at Level 6"))
    try:
        first = run(append_draft(report_id, envelope("stub-run-one", latency_ms=7)))
        second = run(append_draft(report_id, envelope("stub-run-two", latency_ms=9)))

        assert first["version"] == 1
        assert second["version"] == 2

        async def read() -> list[tuple[int, str, str, str, object, int, int, int]]:
            async with connection() as conn:
                rows = await conn.fetch(
                    """
                    select version, provider_ref, raw_json::text,
                           validation::text, validation_errors,
                           latency_ms, tokens_in, tokens_out
                    from ai_drafts
                    where report_id = $1
                    order by version
                    """,
                    report_id,
                )
                return [
                    (
                        row["version"],
                        row["provider_ref"],
                        row["raw_json"],
                        row["validation"],
                        row["validation_errors"],
                        row["latency_ms"],
                        row["tokens_in"],
                        row["tokens_out"],
                    )
                    for row in rows
                ]

        rows = run(read())
        assert [row[0] for row in rows] == [1, 2]
        assert [row[1] for row in rows] == ["stub-run-one", "stub-run-two"]
        first_envelope = envelope("unused", latency_ms=0)
        assert json.loads(rows[0][2]) == {
            key: first_envelope[key]
            for key in (
                "observed_facts",
                "assumptions",
                "missing_information",
                "proposed_category",
                "proposed_urgency",
                "suggested_owner_role",
                "suggested_action",
                "confidence",
                "needs_escalation",
                "escalation_reason",
                "citations",
            )
        }
        assert rows[0][3] == "valid"
        assert json.loads(rows[0][4]) == []
        assert rows[1][3] == "valid"
        assert json.loads(rows[1][4]) == []
        assert rows[0][5:] == (7, 21, 34)
        assert rows[1][5:] == (9, 21, 34)

        report = run(get_report(report_id))
        assert report is not None
        latest_draft = json.loads(report["latest_draft"])
        assert latest_draft["version"] == 2
        assert latest_draft["validation_errors"] == []
    finally:
        run(cleanup(report_id))


def test_service_rejects_a_fabricated_quote_against_current_corpus() -> None:
    report_id = run(create_report(REPORTER_ID, "Guardrail missing at Level 6"))
    document_id, doc_ref = run(create_approved_source())
    try:
        draft = run(
            append_draft(
                report_id,
                cited_envelope(
                    document_id,
                    doc_ref,
                    "Install a temporary guardrail.",
                ),
            )
        )

        errors = json.loads(draft["validation_errors"])
        assert draft["validation"] == "invalid"
        assert CITATION_QUOTE_NOT_VERBATIM in errors
    finally:
        run(cleanup_with_source(report_id, document_id))
