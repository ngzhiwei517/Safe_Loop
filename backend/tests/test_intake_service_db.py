"""Exercise clarification rounds and failure safety against Postgres."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
import json
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.ai.intake_graph import IntakeState
from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, ReportStatus, Role
from app.domain.transitions import TransitionError
from app.services import intake_service
from app.services.intake_service import answer_clarification, run_intake
from app.services.report_service import Actor, create_report, transition_report

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
MANDARIN_REPORTER_ID = UUID("00000000-0000-0000-0000-000000000002")
_test_loop: asyncio.AbstractEventLoop | None = None
T = TypeVar("T")


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Share one pool without coupling this module to another test loop."""
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
        await conn.execute("delete from reports where id = $1", report_id)


async def submitted_report(
    reporter_id: UUID,
    *,
    lang_original: str = "en",
) -> UUID:
    report_id = await create_report(
        reporter_id,
        f"Unsafe {uuid4()}",
        lang_original=lang_original,
    )
    await transition_report(
        report_id,
        ReportStatus.SUBMITTED,
        Actor(ActorType.HUMAN, reporter_id, Role.REPORTER),
    )
    return report_id


def test_vague_mandarin_report_parks_with_at_most_two_localised_questions() -> None:
    report_id = run(submitted_report(MANDARIN_REPORTER_ID, lang_original="zh-CN"))
    try:
        assert run(run_intake(report_id)) is True

        async def read() -> tuple[str, list[tuple[str, str]]]:
            async with connection() as conn:
                status_value = await conn.fetchval(
                    "select status::text from reports where id = $1",
                    report_id,
                )
                rows = await conn.fetch(
                    """
                    select gap, question from clarifications
                    where report_id = $1 order by created_at, id
                    """,
                    report_id,
                )
                return str(status_value), [
                    (str(row["gap"]), str(row["question"])) for row in rows
                ]

        status_value, questions = run(read())
        assert status_value == "clarifying"
        assert 1 <= len(questions) <= 2
        assert all(gap in {"hazard_detail", "location", "activity"} for gap, _ in questions)
        assert all(
            any("\u4e00" <= character <= "\u9fff" for character in question)
            for _, question in questions
        )
    finally:
        run(cleanup(report_id))


def test_complete_submitted_report_drafts_without_clarification() -> None:
    async def make_complete_report() -> UUID:
        report_id = await create_report(
            REPORTER_ID,
            "The Level 6 guardrail is missing beside formwork.",
            location_text="Level 6 east edge",
            activity="Formwork",
        )
        await transition_report(
            report_id,
            ReportStatus.SUBMITTED,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
        return report_id

    report_id = run(make_complete_report())
    try:
        assert run(run_intake(report_id)) is True

        async def read() -> tuple[str, int, str, int]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select status::text,
                      (select count(*) from clarifications where report_id = $1),
                      (select event from audit_log where report_id = $1
                       order by created_at desc, id desc limit 1),
                      (select count(*) from ai_drafts where report_id = $1)
                    from reports where id = $1
                    """,
                    report_id,
                )
                assert row is not None
                return row[0], row[1], row[2], row[3]

        assert run(read()) == (
            "ai_drafted",
            0,
            "draft_without_clarification",
            1,
        )
    finally:
        run(cleanup(report_id))


def test_cap_prevents_a_third_round_and_persists_outstanding_gaps() -> None:
    report_id = run(submitted_report(REPORTER_ID))
    try:
        run(transition_report(report_id, ReportStatus.CLARIFYING, Actor.ai()))

        async def set_cap() -> None:
            async with connection() as conn:
                await conn.execute(
                    "update reports set clarify_rounds = 2 where id = $1",
                    report_id,
                )

        run(set_cap())
        assert run(run_intake(report_id)) is True

        async def read() -> tuple[str, int, object, int]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select status::text, clarify_rounds, missing_information,
                      (select count(*) from clarifications where report_id = $1)
                    from reports where id = $1
                    """,
                    report_id,
                )
                assert row is not None
                return row[0], row[1], row[2], row[3]

        status_value, rounds, raw_gaps, question_count = run(read())
        gaps = json.loads(raw_gaps) if isinstance(raw_gaps, str) else raw_gaps
        assert status_value == "ai_drafted"
        assert rounds == 2
        assert gaps == ["hazard_detail", "location", "activity"]
        assert question_count == 0
    finally:
        run(cleanup(report_id))


def test_answering_two_questions_increments_once_then_preserves_the_last_gap() -> None:
    report_id = run(submitted_report(REPORTER_ID))
    try:
        assert run(run_intake(report_id)) is True

        async def question_ids() -> list[UUID]:
            async with connection() as conn:
                return await conn.fetch(
                    """
                    select id from clarifications
                    where report_id = $1 and round = 1
                    order by created_at, id
                    """,
                    report_id,
                )

        ids = [row["id"] for row in run(question_ids())]
        actor = Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER)
        for index, clarification_id in enumerate(ids):
            result = run(
                answer_clarification(
                    report_id,
                    clarification_id,
                    actor,
                    f"Answer {index + 1}",
                )
            )
            assert result.rerun is (index == len(ids) - 1)

        async def report_state() -> tuple[str, int, object, int]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select status::text, clarify_rounds, missing_information,
                      (select count(*) from clarifications where report_id = $1)
                    from reports where id = $1
                    """,
                    report_id,
                )
                assert row is not None
                return row[0], row[1], row[2], row[3]

        assert run(run_intake(report_id)) is True
        status_value, rounds, raw_gaps, question_count = run(report_state())
        gaps = json.loads(raw_gaps) if isinstance(raw_gaps, str) else raw_gaps
        assert status_value == "ai_drafted"
        assert rounds == 1
        assert gaps == ["activity"]
        assert question_count == 2
    finally:
        run(cleanup(report_id))


def test_graph_exception_leaves_submitted_status_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = run(submitted_report(REPORTER_ID))
    try:
        async def fail_graph(_: IntakeState) -> IntakeState:
            raise RuntimeError("fixture graph failure")

        monkeypatch.setattr(intake_service, "_invoke_graph", fail_graph)
        assert run(run_intake(report_id)) is False

        async def read() -> tuple[str, int, int]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select status::text,
                      (select count(*) from clarifications where report_id = $1),
                      (select count(*) from audit_log where report_id = $1)
                    from reports where id = $1
                    """,
                    report_id,
                )
                assert row is not None
                return row[0], row[1], row[2]

        assert run(read()) == ("submitted", 0, 2)
    finally:
        run(cleanup(report_id))


def test_failed_transition_rolls_back_the_appended_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def make_complete_report() -> UUID:
        report_id = await create_report(
            REPORTER_ID,
            "The Level 6 guardrail is missing beside formwork.",
            location_text="Level 6 east edge",
            activity="Formwork",
        )
        await transition_report(
            report_id,
            ReportStatus.SUBMITTED,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
        return report_id

    report_id = run(make_complete_report())
    try:
        async def fail_transition(*_: object, **__: object) -> None:
            raise TransitionError("fixture_transition_failure", "fixture failure")

        monkeypatch.setattr(intake_service, "transition_report", fail_transition)
        assert run(run_intake(report_id)) is False

        async def read() -> tuple[str, int]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select status::text,
                      (select count(*) from ai_drafts where report_id = $1)
                    from reports where id = $1
                    """,
                    report_id,
                )
                assert row is not None
                return row[0], row[1]

        assert run(read()) == ("submitted", 0)
    finally:
        run(cleanup(report_id))
