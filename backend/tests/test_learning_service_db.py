"""Prove public lesson delivery, quiz identity, ranking, and throttling in Postgres."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.config import get_settings
from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, Role
from app.services.learning_service import (
    LearningError,
    get_public_briefing,
    list_learning_briefings,
    submit_quiz_answer,
)
from app.services.rate_limit_service import subject_hash
from app.services.report_service import Actor

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


def locale_map(value: str) -> dict[str, str]:
    return {"en": value, "zh-CN": f"中文 {value}"}


async def seed_report(*, activity: str = "Formwork", location: str = "Level 6") -> UUID:
    async with connection() as conn:
        report_id = await conn.fetchval(
            """
            insert into reports (
              reporter_id, status, description_original, activity, location_text
            )
            values ($1, 'lesson_published'::report_status, 'learning fixture', $2, $3)
            returning id
            """,
            REPORTER_ID,
            activity,
            location,
        )
    assert isinstance(report_id, UUID)
    return report_id


async def seed_briefing(
    report_id: UUID,
    *,
    version: int = 1,
    target_activity: str | None = "Formwork",
    target_location: str | None = "Level 6",
    active: bool = True,
    published: bool = True,
    approved_at: datetime | None = None,
) -> tuple[UUID, str, list[UUID]]:
    now = datetime.now(timezone.utc)
    valid_from = now - timedelta(days=1 if active else 30)
    valid_to = now + timedelta(days=30) if active else now - timedelta(days=1)
    token = f"lesson-{uuid4().hex}"
    status = "published" if published else "draft"
    async with connection() as conn:
        async with conn.transaction():
            briefing_id = await conn.fetchval(
                """
                insert into briefings (
                  report_id, version, body, status, target_activity, target_location,
                  valid_from, valid_to, qr_token, approved_by, approved_at
                )
                values (
                  $1, $2, $3::jsonb, $4::briefing_status, $5, $6, $7, $8, $9,
                  case when $4 = 'published' then $10::uuid else null::uuid end,
                  case when $4 = 'published' then $11::timestamptz else null::timestamptz end
                )
                returning id
                """,
                report_id,
                version,
                json.dumps(
                    locale_map(
                        "## What happened\nA cover moved.\n\n"
                        "## Why it matters\nA fall was possible.\n\n"
                        "## What to do differently\nSecure the cover."
                    ),
                    ensure_ascii=False,
                ),
                status,
                target_activity,
                target_location,
                valid_from,
                valid_to,
                token,
                REVIEWER_ID,
                approved_at or now,
            )
            assert isinstance(briefing_id, UUID)
            question_ids: list[UUID] = []
            for position in range(1, 4):
                question_id = await conn.fetchval(
                    """
                    insert into quiz_questions (
                      briefing_id, position, question, explanation, options, correct_option
                    )
                    values ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, 0)
                    returning id
                    """,
                    briefing_id,
                    position,
                    json.dumps(locale_map(f"Question {position}?"), ensure_ascii=False),
                    json.dumps(locale_map(f"Explanation {position}."), ensure_ascii=False),
                    json.dumps(
                        [locale_map(f"Option {option}") for option in range(1, 5)],
                        ensure_ascii=False,
                    ),
                )
                assert isinstance(question_id, UUID)
                question_ids.append(question_id)
    return briefing_id, token, question_ids


async def cleanup_reports(*report_ids: UUID) -> None:
    async with connection() as conn:
        await conn.execute("delete from reports where id = any($1::uuid[])", list(report_ids))


def test_public_lookup_returns_locale_maps_without_answers_and_rejects_inactive() -> None:
    active_report = run(seed_report())
    expired_report = run(seed_report())
    draft_report = run(seed_report())
    _, active_token, _ = run(seed_briefing(active_report))
    _, expired_token, _ = run(seed_briefing(expired_report, active=False))
    _, draft_token, _ = run(seed_briefing(draft_report, published=False))
    try:
        result = run(get_public_briefing(active_token))
        assert result["body"]["en"]
        assert result["body"]["zh-CN"]
        questions = result["quiz_questions"]
        assert isinstance(questions, list) and len(questions) == 3
        assert all("correct_option" not in question for question in questions)

        for token in (expired_token, draft_token):
            with pytest.raises(LearningError) as error:
                run(get_public_briefing(token))
            assert error.value.code == "briefing_inactive"
    finally:
        run(cleanup_reports(active_report, expired_report, draft_report))


def test_quiz_records_anonymous_and_signed_in_responses() -> None:
    report_id = run(seed_report())
    _, token, questions = run(seed_briefing(report_id))
    try:
        anonymous = run(
            submit_quiz_answer(
                token,
                questions[0],
                0,
                actor=None,
                client_ip="198.51.100.21",
            )
        )
        signed = run(
            submit_quiz_answer(
                token,
                questions[1],
                1,
                actor=Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE),
                client_ip="198.51.100.22",
            )
        )
        assert anonymous["is_correct"] is True
        assert signed["is_correct"] is False

        async def identities() -> list[object]:
            async with connection() as conn:
                rows = await conn.fetch(
                    """
                    select respondent_id from quiz_responses
                    where id = any($1::uuid[]) order by created_at, id
                    """,
                    [anonymous["response_id"], signed["response_id"]],
                )
                return [row["respondent_id"] for row in rows]

        assert run(identities()) == [None, RESPONSIBLE_ID]
    finally:
        run(cleanup_reports(report_id))


def test_rate_limit_fires_at_configured_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = run(seed_report())
    _, token, questions = run(seed_briefing(report_id))
    client_ip = "198.51.100.23"
    monkeypatch.setenv("QUIZ_RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        for _ in range(2):
            run(
                submit_quiz_answer(
                    token,
                    questions[0],
                    0,
                    actor=None,
                    client_ip=client_ip,
                )
            )
        with pytest.raises(LearningError) as error:
            run(
                submit_quiz_answer(
                    token,
                    questions[0],
                    0,
                    actor=None,
                    client_ip=client_ip,
                )
            )
        assert error.value.code == "quiz_rate_limited"
    finally:
        get_settings.cache_clear()

        async def cleanup_limit() -> None:
            async with connection() as conn:
                await conn.execute(
                    """
                    delete from request_rate_limits
                    where scope = 'quiz_submission' and subject_hash = $1
                    """,
                    subject_hash(client_ip),
                )

        run(cleanup_limit())
        run(cleanup_reports(report_id))


def test_learning_feed_ranks_context_then_newest_and_tracks_full_quiz() -> None:
    targeted_report = run(seed_report(activity="Formwork", location="Level 6"))
    newest_report = run(seed_report(activity="Electrical", location="Level 2"))
    _, old_token, _ = run(
        seed_briefing(
            targeted_report,
            version=1,
            approved_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
    )
    latest_id, latest_token, questions = run(
        seed_briefing(
            targeted_report,
            version=2,
            approved_at=datetime.now(timezone.utc) - timedelta(days=4),
        )
    )
    newest_id, _, _ = run(
        seed_briefing(
            newest_report,
            target_activity=None,
            target_location=None,
            approved_at=datetime.now(timezone.utc),
        )
    )

    async def assign_context() -> None:
        async with connection() as conn:
            await conn.execute(
                """
                insert into report_assignments (
                  report_id, assignee_id, case_role, due_at
                )
                values ($1, $2, 'responsible'::case_role, now() + interval '7 days')
                """,
                targeted_report,
                RESPONSIBLE_ID,
            )

    run(assign_context())
    actor = Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE)
    try:
        before = run(list_learning_briefings(actor))
        assert [item["id"] for item in before[:2]] == [latest_id, newest_id]
        assert before[0]["target_match"] is True
        assert before[0]["quiz_answered"] is False
        assert all(item["qr_token"] != old_token for item in before)

        for index, question_id in enumerate(questions):
            run(
                submit_quiz_answer(
                    latest_token,
                    question_id,
                    0,
                    actor=actor,
                    client_ip=f"198.51.100.{30 + index}",
                )
            )

        after = run(list_learning_briefings(actor))
        assert after[0]["answered_count"] == 3
        assert after[0]["quiz_answered"] is True
    finally:
        run(cleanup_reports(targeted_report, newest_report))
