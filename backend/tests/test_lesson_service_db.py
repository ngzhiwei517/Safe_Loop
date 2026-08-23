"""Prove lessons persist atomically from accepted closure material in Postgres."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import (
    ActorType,
    ReportStatus,
    ReviewDecision,
    Role,
)
from app.domain.transitions import TransitionError
from app.rag.retrieve import RetrievedChunk
from app.services import lesson_service
from app.services.action_service import submit_action
from app.services.lesson_service import run_lesson
from app.services.report_service import Actor, create_report, transition_report
from app.services.review_service import review_report
from app.services.verification_service import verify_report

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
RESPONSIBLE_ID = UUID("00000000-0000-0000-0000-000000000004")
T = TypeVar("T")
_test_loop: asyncio.AbstractEventLoop | None = None


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Share one pool while keeping this module's event loop isolated."""
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


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute(
            """
            delete from notifications
            where entity_id = $1 or payload ->> 'report_id' = $1::text
            """,
            report_id,
        )
        await conn.execute("delete from reports where id = $1", report_id)


async def add_evidence(report_id: UUID, marker: str) -> UUID:
    async with connection() as conn:
        media_id = await conn.fetchval(
            """
            insert into report_media (
              report_id, storage_path, mime_type, phase, caption
            )
            values ($1, $2, 'image/jpeg', 'evidence'::media_phase, $3)
            returning id
            """,
            report_id,
            f"{RESPONSIBLE_ID}/{report_id}/{uuid4()}.jpg",
            marker,
        )
    assert isinstance(media_id, UUID)
    return media_id


async def closed_case_with_rejected_cycle() -> tuple[UUID, UUID]:
    report_id = await create_report(
        REPORTER_ID,
        "REJECTED_ORIGINAL_MARKER must not be copied into the lesson.",
        location_text="Level 6 east edge",
        activity="Formwork",
    )
    reporter = Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER)
    reviewer = Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
    responsible = Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE)
    await transition_report(report_id, ReportStatus.SUBMITTED, reporter)
    await transition_report(report_id, ReportStatus.AI_DRAFTED, Actor.ai())
    await transition_report(report_id, ReportStatus.UNDER_REVIEW, Actor.system())
    reviewed = await review_report(
        report_id,
        reviewer,
        decision=ReviewDecision.APPROVE,
        target=ReportStatus.ACTION_ASSIGNED,
        corrected_action="Install and secure the missing guardrail.",
        correction_reason="Use the action approved during review.",
        assignee_id=RESPONSIBLE_ID,
        due_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    assert reviewed.corrective_action_id is not None
    action_id = reviewed.corrective_action_id

    rejected_media = await add_evidence(report_id, "REJECTED_EVIDENCE_MARKER")
    await submit_action(
        report_id,
        action_id,
        responsible,
        completed_note="REJECTED_COMPLETION_MARKER",
        media_ids=[rejected_media],
    )
    await verify_report(
        report_id,
        reviewer,
        passed=False,
        checklist={"hazard_removed": False},
        notes="REJECTED_VERIFICATION_MARKER",
        reason="The lower guardrail anchor still moves under load.",
        new_due_at=datetime.now(timezone.utc) + timedelta(days=3),
    )

    accepted_media = await add_evidence(
        report_id,
        "Completed guardrail with secured anchors",
    )
    await submit_action(
        report_id,
        action_id,
        responsible,
        completed_note="The guardrail and both anchors were secured.",
        media_ids=[accepted_media],
    )
    await verify_report(
        report_id,
        reviewer,
        passed=True,
        checklist={"hazard_removed": True, "anchors_secure": True},
        notes="The guardrail and both anchors passed the final pull test.",
    )
    return report_id, action_id


async def fake_retrieve(_: str) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            content="Workers must install guardrails before work starts.",
            document_id=UUID("20000000-0000-0000-0000-000000000001"),
            doc_ref="WAH-001",
            revision="3",
            section="4.2",
            page=7,
            similarity=0.92,
        ),
        RetrievedChunk(
            content="高处作业前必须检查防护栏。防护栏必须牢固。",
            document_id=UUID("20000000-0000-0000-0000-000000000002"),
            doc_ref="高处-001",
            revision="2",
            section="4.2",
            page=8,
            similarity=0.9,
        ),
    ]


def decoded(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


async def read_lesson(report_id: UUID) -> tuple[object, list[object]]:
    async with connection() as conn:
        briefing = await conn.fetchrow(
            """
            select briefing.*, report.status::text as report_status,
              (
                select actor_type::text
                from audit_log
                where report_id = report.id and event = 'draft_lesson'
                order by created_at desc, id desc
                limit 1
              ) as lesson_actor_type
            from reports report
            left join briefings briefing on briefing.report_id = report.id
            where report.id = $1
            """,
            report_id,
        )
        questions = await conn.fetch(
            """
            select * from quiz_questions
            where briefing_id = $1
            order by position
            """,
            briefing["id"] if briefing is not None else None,
        )
    assert briefing is not None
    return briefing, list(questions)


def test_closed_case_creates_one_bilingual_draft_and_three_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lesson_service, "retrieve_chunks", fake_retrieve)
    report_id, _ = run(closed_case_with_rejected_cycle())
    try:
        assert run(run_lesson(report_id)) is True
        briefing, questions = run(read_lesson(report_id))
        body = decoded(briefing["body"])
        assert isinstance(body, dict)
        assert set(body) == {"en", "zh-CN"}
        assert all(isinstance(body[locale], str) and body[locale].strip() for locale in body)
        assert "防护栏" in body["zh-CN"]
        assert briefing["version"] == 1
        assert briefing["status"] == "draft"
        assert briefing["report_status"] == "lesson_drafted"
        assert briefing["lesson_actor_type"] == "ai"
        assert briefing["target_activity"] == "Formwork"
        assert briefing["target_location"] == "Level 6 east edge"
        assert len(questions) == 3
        for position, question in enumerate(questions, start=1):
            assert question["position"] == position
            question_map = decoded(question["question"])
            explanation_map = decoded(question["explanation"])
            options = decoded(question["options"])
            assert isinstance(question_map, dict)
            assert isinstance(explanation_map, dict)
            assert set(question_map) == {"en", "zh-CN"}
            assert set(explanation_map) == {"en", "zh-CN"}
            assert isinstance(options, list) and len(options) == 4
            assert all(set(option) == {"en", "zh-CN"} for option in options)
            assert 0 <= question["correct_option"] < 4

        stored_text = json.dumps(
            {"body": body, "questions": [dict(question) for question in questions]},
            ensure_ascii=False,
            default=str,
        )
        assert "REJECTED_ORIGINAL_MARKER" not in stored_text
        assert "REJECTED_EVIDENCE_MARKER" not in stored_text
        assert "REJECTED_COMPLETION_MARKER" not in stored_text
        assert "REJECTED_VERIFICATION_MARKER" not in stored_text

        assert run(run_lesson(report_id)) is False
        _, after_questions = run(read_lesson(report_id))
        assert len(after_questions) == 3
    finally:
        run(cleanup(report_id))


def test_transition_failure_rolls_back_briefing_and_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lesson_service, "retrieve_chunks", fake_retrieve)
    report_id, _ = run(closed_case_with_rejected_cycle())

    async def fail_transition(*_: object, **__: object) -> None:
        raise TransitionError("illegal_transition", "forced lesson transition failure")

    monkeypatch.setattr(lesson_service, "transition_report", fail_transition)
    try:
        assert run(run_lesson(report_id)) is False

        async def counts() -> tuple[str, int, int]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select status::text,
                      (select count(*) from briefings where report_id = $1)::integer,
                      (
                        select count(*)
                        from quiz_questions question
                        join briefings briefing on briefing.id = question.briefing_id
                        where briefing.report_id = $1
                      )::integer
                    from reports where id = $1
                    """,
                    report_id,
                )
                assert row is not None
                return row[0], row[1], row[2]

        assert run(counts()) == ("verified_closed", 0, 0)
    finally:
        run(cleanup(report_id))


def test_lesson_allocates_the_next_briefing_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lesson_service, "retrieve_chunks", fake_retrieve)
    report_id, _ = run(closed_case_with_rejected_cycle())

    async def seed_prior_version() -> None:
        async with connection() as conn:
            await conn.execute(
                """
                insert into briefings (report_id, version, body, status)
                values (
                  $1, 3, '{"en":"Earlier draft","zh-CN":"较早的草稿"}'::jsonb,
                  'draft'::briefing_status
                )
                """,
                report_id,
            )

    try:
        run(seed_prior_version())
        assert run(run_lesson(report_id)) is True

        async def versions() -> list[int]:
            async with connection() as conn:
                rows = await conn.fetch(
                    """
                    select version from briefings
                    where report_id = $1 order by version
                    """,
                    report_id,
                )
                return [int(row["version"]) for row in rows]

        assert run(versions()) == [3, 4]
    finally:
        run(cleanup(report_id))
