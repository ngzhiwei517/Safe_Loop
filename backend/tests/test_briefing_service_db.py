"""Prove lesson publication and immutable revisions against Postgres guards."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, TypeVar
from uuid import UUID

import asyncpg
import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, Role
from app.domain.transitions import TransitionError
from app.services import briefing_service
from app.services.briefing_service import (
    BriefingEdit,
    BriefingError,
    QuizEdit,
    get_managed_briefing,
    publish_briefing,
    save_briefing,
)
from app.services.report_service import Actor

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
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


def lesson_edit(marker: str = "approved") -> BriefingEdit:
    return BriefingEdit(
        body={
            "en": f"Verified case lesson {marker}.",
            "zh-CN": f"已核实个案课程 {marker}。",
        },
        target_activity="Formwork",
        target_location="Level 6",
        valid_from=datetime.now(timezone.utc),
        valid_to=datetime.now(timezone.utc) + timedelta(days=30),
        questions=[
            QuizEdit(
                position=position,
                question={
                    "en": f"Question {position} {marker}?",
                    "zh-CN": f"问题 {position} {marker}？",
                },
                explanation={
                    "en": f"Explanation {position} {marker}.",
                    "zh-CN": f"解释 {position} {marker}。",
                },
                options=[
                    {
                        "en": f"Option {option} {marker}",
                        "zh-CN": f"选项 {option} {marker}",
                    }
                    for option in range(1, 5)
                ],
                correct_option=position % 4,
            )
            for position in range(1, 4)
        ],
    )


async def seed_draft(edit: BriefingEdit | None = None) -> tuple[UUID, UUID]:
    content = edit or lesson_edit()
    async with connection() as conn:
        async with conn.transaction():
            report_id = await conn.fetchval(
                """
                insert into reports (
                  reporter_id, status, description_original, location_text, activity
                )
                values (
                  $1, 'lesson_drafted'::report_status, 'verified fixture',
                  'Level 6', 'Formwork'
                )
                returning id
                """,
                REPORTER_ID,
            )
            assert isinstance(report_id, UUID)
            briefing_id = await conn.fetchval(
                """
                insert into briefings (
                  report_id, version, body, status, target_activity,
                  target_location, valid_from, valid_to
                )
                values (
                  $1, 1, $2::jsonb, 'draft'::briefing_status, $3, $4, $5, $6
                )
                returning id
                """,
                report_id,
                json.dumps(content.body, ensure_ascii=False),
                content.target_activity,
                content.target_location,
                content.valid_from,
                content.valid_to,
            )
            assert isinstance(briefing_id, UUID)
            await conn.executemany(
                """
                insert into quiz_questions (
                  briefing_id, position, question, explanation, options, correct_option
                )
                values ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6)
                """,
                [
                    (
                        briefing_id,
                        question.position,
                        json.dumps(question.question, ensure_ascii=False),
                        json.dumps(question.explanation, ensure_ascii=False),
                        json.dumps(question.options, ensure_ascii=False),
                        question.correct_option,
                    )
                    for question in content.questions
                ],
            )
    return report_id, briefing_id


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute("delete from reports where id = $1", report_id)


def reviewer() -> Actor:
    return Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)


def decoded(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def test_publish_sets_approval_token_and_transitions_atomically() -> None:
    report_id, briefing_id = run(seed_draft())
    try:
        draft = run(get_managed_briefing(briefing_id, reviewer()))
        assert draft["available_transitions"] == [
            {
                "event": "publish_lesson",
                "target": "lesson_published",
                "requires_reason": False,
            }
        ]
        result = run(publish_briefing(briefing_id, reviewer()))
        assert result["status"] == "published"
        assert result["available_transitions"] == []
        assert result["approved_by"] == REVIEWER_ID
        assert result["approved_at"] is not None
        token = result["qr_token"]
        assert isinstance(token, str) and len(token) >= 22

        async def state() -> tuple[str, int]:
            async with connection() as conn:
                status = await conn.fetchval(
                    "select status::text from reports where id = $1", report_id
                )
                audits = await conn.fetchval(
                    """
                    select count(*) from audit_log
                    where report_id = $1 and event = 'publish_lesson'
                      and actor_type = 'human'::actor_type and actor_id = $2
                    """,
                    report_id,
                    REVIEWER_ID,
                )
                return str(status), int(audits)

        assert run(state()) == ("lesson_published", 1)
    finally:
        run(cleanup(report_id))


def test_missing_chinese_never_partially_publishes() -> None:
    edit = lesson_edit()
    edit = BriefingEdit(
        body={"en": edit.body["en"], "zh-CN": ""},
        questions=edit.questions,
        valid_from=edit.valid_from,
        valid_to=edit.valid_to,
    )
    report_id, briefing_id = run(seed_draft(edit))
    try:
        with pytest.raises(BriefingError) as error:
            run(publish_briefing(briefing_id, reviewer()))
        assert error.value.code == "briefing_both_locales_required"

        async def state() -> tuple[str, str, object, object]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select report.status::text as report_status,
                           briefing.status::text as briefing_status,
                           briefing.qr_token, briefing.approved_at
                    from reports report
                    join briefings briefing on briefing.report_id = report.id
                    where briefing.id = $1
                    """,
                    briefing_id,
                )
                assert row is not None
                return row[0], row[1], row[2], row[3]

        assert run(state()) == ("lesson_drafted", "draft", None, None)
    finally:
        run(cleanup(report_id))


def test_publish_requires_an_expiring_validity_window() -> None:
    edit = lesson_edit()
    edit = BriefingEdit(
        body=edit.body,
        questions=edit.questions,
        valid_from=None,
        valid_to=None,
    )
    report_id, briefing_id = run(seed_draft(edit))
    try:
        with pytest.raises(BriefingError) as error:
            run(publish_briefing(briefing_id, reviewer()))
        assert error.value.code == "briefing_validity_required"
    finally:
        run(cleanup(report_id))


def test_editing_published_creates_version_two_without_mutating_version_one() -> None:
    original = lesson_edit("original")
    report_id, briefing_id = run(seed_draft(original))
    try:
        run(publish_briefing(briefing_id, reviewer()))
        revised = run(save_briefing(briefing_id, reviewer(), lesson_edit("revised")))
        assert revised["id"] != briefing_id
        assert revised["version"] == 2
        assert revised["status"] == "draft"
        assert revised["available_transitions"] == [
            {
                "event": "republish_lesson",
                "target": "lesson_published",
                "requires_reason": False,
            }
        ]

        async def versions() -> tuple[object, object, str, int]:
            async with connection() as conn:
                rows = await conn.fetch(
                    """
                    select version, body, status::text
                    from briefings where report_id = $1 order by version
                    """,
                    report_id,
                )
                report_status = await conn.fetchval(
                    "select status::text from reports where id = $1", report_id
                )
                revisions = await conn.fetchval(
                    """
                    select count(*) from audit_log
                    where report_id = $1 and event = 'revise_lesson'
                    """,
                    report_id,
                )
                return rows, report_status, str(report_status), int(revisions)

        rows, _, report_status, revisions = run(versions())
        assert len(rows) == 2
        assert decoded(rows[0]["body"]) == original.body
        assert rows[0]["status"] == "published"
        assert decoded(rows[1]["body"]) == lesson_edit("revised").body
        assert report_status == "lesson_published"
        assert revisions == 1

        republished = run(
            publish_briefing(cast_uuid(revised["id"]), reviewer())
        )
        assert republished["status"] == "published"
        assert republished["version"] == 2
    finally:
        run(cleanup(report_id))


def cast_uuid(value: object) -> UUID:
    assert isinstance(value, UUID)
    return value


def test_transition_failure_rolls_back_publication_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id, briefing_id = run(seed_draft())

    async def fail_transition(*_: object, **__: object) -> None:
        raise TransitionError("illegal_transition", "forced publication failure")

    monkeypatch.setattr(briefing_service, "transition_report", fail_transition)
    try:
        with pytest.raises(TransitionError):
            run(publish_briefing(briefing_id, reviewer()))

        async def state() -> tuple[str, object, object]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    "select status::text, qr_token, approved_at from briefings where id = $1",
                    briefing_id,
                )
                assert row is not None
                return row[0], row[1], row[2]

        assert run(state()) == ("draft", None, None)
    finally:
        run(cleanup(report_id))


def test_raw_sql_cannot_rewrite_published_body_or_quiz() -> None:
    report_id, briefing_id = run(seed_draft())
    try:
        run(publish_briefing(briefing_id, reviewer()))

        async def raw_updates() -> tuple[str | None, str | None]:
            async with connection() as conn:
                briefing_code: str | None = None
                quiz_code: str | None = None
                try:
                    await conn.execute(
                        "update briefings set target_location = 'changed' where id = $1",
                        briefing_id,
                    )
                except asyncpg.PostgresError as error:
                    briefing_code = error.sqlstate
                try:
                    await conn.execute(
                        """
                        update quiz_questions set correct_option = 0
                        where briefing_id = $1 and position = 1
                        """,
                        briefing_id,
                    )
                except asyncpg.PostgresError as error:
                    quiz_code = error.sqlstate
                return briefing_code, quiz_code

        assert run(raw_updates()) == ("55000", "55000")
    finally:
        run(cleanup(report_id))
