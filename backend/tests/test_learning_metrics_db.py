"""Reconcile learning outcomes and repeat hazards against real Postgres rows."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, Role
from app.services.metrics_service import get_metrics_summary
from app.services.report_service import Actor

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
RESPONSIBLE_ID = UUID("00000000-0000-0000-0000-000000000004")
CREW_ID = UUID("00000000-0000-0000-0000-000000000005")
_test_loop: asyncio.AbstractEventLoop | None = None


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Share one pool while keeping fixture cleanup explicit."""
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


def run(coroutine):  # type: ignore[no-untyped-def]
    assert _test_loop is not None
    return _test_loop.run_until_complete(coroutine)


async def _insert_closed_report(
    conn: asyncpg.pool.PoolConnectionProxy[asyncpg.Record],
    report_id: UUID,
    *,
    status: str,
    category: str,
    location: str,
    closed_at: datetime,
    corrected_category: str | None = None,
    rework_count: int = 0,
) -> None:
    await conn.execute(
        """
        insert into reports (
          id, reporter_id, status, description_original, location_text,
          submitted_at, closed_at, created_at, updated_at
        )
        values ($1, $2, $3::report_status, $4, $5, $6, $6, $6, $6)
        """,
        report_id,
        REPORTER_ID,
        status,
        f"learning metric fixture {report_id}",
        location,
        closed_at,
    )
    await conn.execute(
        """
        insert into ai_drafts (
          report_id, version, provider, provider_ref, raw_json,
          observed_facts, assumptions, missing_information, proposed_category
        )
        values ($1, 1, 'stub', $2, '{}'::jsonb, '[]'::jsonb,
                '[]'::jsonb, '[]'::jsonb, $3)
        """,
        report_id,
        f"fixture-{report_id}",
        category,
    )
    if corrected_category is not None:
        await conn.execute(
            """
            insert into review_decisions (
              report_id, reviewer_id, decision, corrections, correction_reason
            )
            values (
              $1, $2, 'approve'::review_decision,
              $3::jsonb, 'Reviewer set the final category.'
            )
            """,
            report_id,
            REVIEWER_ID,
            json.dumps(
                {
                    "category": {
                        "before": category,
                        "after": corrected_category,
                    }
                }
            ),
        )
    assignment_id = await conn.fetchval(
        """
        insert into report_assignments (report_id, assignee_id, case_role, due_at)
        values ($1, $2, 'responsible'::case_role, $3)
        returning id
        """,
        report_id,
        RESPONSIBLE_ID,
        closed_at,
    )
    await conn.execute(
        """
        insert into corrective_actions (
          report_id, assignment_id, action_text, status, rework_count, due_at
        )
        values ($1, $2, 'Fixture action', 'verified'::action_status, $3, $4)
        """,
        report_id,
        assignment_id,
        rework_count,
        closed_at,
    )


async def _create_fixture() -> tuple[list[UUID], UUID, UUID, str, str]:
    report_ids = [uuid4() for _ in range(4)]
    suffix = uuid4().hex[:10]
    category = f"fixture_category_{suffix}"
    location = f"Fixture Zone {suffix}"
    now = datetime.now(timezone.utc)
    briefing_id = uuid4()
    question_ids = [uuid4(), uuid4()]
    async with connection() as conn:
        async with conn.transaction():
            await _insert_closed_report(
                conn,
                report_ids[0],
                status="verified_closed",
                category=category,
                location=location,
                closed_at=now - timedelta(days=20),
                rework_count=0,
            )
            await _insert_closed_report(
                conn,
                report_ids[1],
                status="lesson_drafted",
                category="wrong_fixture_category",
                corrected_category=category,
                location=f"  {location}  ",
                closed_at=now - timedelta(days=2),
                rework_count=1,
            )
            await _insert_closed_report(
                conn,
                report_ids[2],
                status="verified_closed",
                category=category,
                location=location,
                closed_at=now - timedelta(days=100),
                rework_count=0,
            )
            await _insert_closed_report(
                conn,
                report_ids[3],
                status="verified_closed",
                category=category,
                location=f"Other {location}",
                closed_at=now - timedelta(days=1),
                rework_count=0,
            )
            await conn.execute(
                """
                insert into briefings (
                  id, report_id, version, body, status, valid_from, valid_to,
                  qr_token, approved_by, approved_at
                )
                values (
                  $1, $2, 1, $3::jsonb, 'published'::briefing_status,
                  $4, $5, $6, $7, $4
                )
                """,
                briefing_id,
                report_ids[0],
                json.dumps({"en": "Fixture lesson", "zh-CN": "测试课程"}),
                now - timedelta(days=1),
                now + timedelta(days=30),
                f"fixture-token-{uuid4().hex}",
                REVIEWER_ID,
            )
            for position, question_id in enumerate(question_ids, start=1):
                await conn.execute(
                    """
                    insert into quiz_questions (
                      id, briefing_id, position, question, explanation,
                      options, correct_option
                    )
                    values ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, 0)
                    """,
                    question_id,
                    briefing_id,
                    position,
                    json.dumps(
                        {
                            "en": f"Fixture question {position}",
                            "zh-CN": f"测试问题 {position}",
                        }
                    ),
                    json.dumps({"en": "Fixture explanation", "zh-CN": "测试说明"}),
                    json.dumps(
                        [
                            {"en": "Safe", "zh-CN": "安全"},
                            {"en": "Unsafe", "zh-CN": "不安全"},
                            {"en": "Wait", "zh-CN": "等待"},
                            {"en": "Ignore", "zh-CN": "忽略"},
                        ]
                    ),
                )
            attempt_time = now - timedelta(hours=1)
            await conn.executemany(
                """
                insert into quiz_responses (
                  question_id, respondent_id, selected_option, is_correct, created_at
                )
                values ($1, $2, $3, $4, $5)
                """,
                [
                    (question_ids[0], CREW_ID, 1, False, attempt_time),
                    (question_ids[0], CREW_ID, 0, True, attempt_time + timedelta(minutes=1)),
                    (question_ids[0], REPORTER_ID, 0, True, attempt_time),
                    (question_ids[0], None, 0, True, attempt_time),
                    (question_ids[1], CREW_ID, 1, False, attempt_time),
                    (question_ids[1], REPORTER_ID, 1, False, attempt_time),
                ],
            )
    return report_ids, question_ids[0], question_ids[1], category, location


async def _direct_learning_totals() -> tuple[int, int, int, int, float | None]:
    async with connection() as conn:
        published_count = int(
            await conn.fetchval(
                """
                select count(distinct report_id)
                from briefings where status = 'published'::briefing_status
                """
            )
        )
        rows = await conn.fetch(
            """
            select response.id, response.question_id, response.respondent_id,
                   response.is_correct, response.created_at
            from quiz_responses response
            join quiz_questions question on question.id = response.question_id
            join briefings briefing on briefing.id = question.briefing_id
            where briefing.status = 'published'::briefing_status
            order by response.created_at, response.id
            """
        )
    identified = [row for row in rows if row["respondent_id"] is not None]
    crew_reach = len({row["respondent_id"] for row in identified})
    anonymous_count = len(rows) - len(identified)
    first: dict[tuple[UUID, UUID], bool] = {}
    for row in identified:
        key = (row["question_id"], row["respondent_id"])
        first.setdefault(key, bool(row["is_correct"]))
    pass_rate = sum(first.values()) / len(first) if first else None
    return published_count, crew_reach, anonymous_count, len(first), pass_rate


async def _responsible_rework_rate() -> float:
    async with connection() as conn:
        value = await conn.fetchval(
            """
            select coalesce(
              count(action.id) filter (where action.rework_count >= 1)::double precision
                / nullif(count(action.id), 0),
              0
            )
            from corrective_actions action
            join report_assignments assignment on assignment.id = action.assignment_id
            where assignment.assignee_id = $1
            """,
            RESPONSIBLE_ID,
        )
    return float(value)


async def _cleanup(report_ids: list[UUID]) -> None:
    async with connection() as conn:
        await conn.execute("delete from reports where id = any($1::uuid[])", report_ids)


def test_learning_and_repeat_metrics_reconcile_with_database_rows() -> None:
    report_ids, question_one, question_two, category, location = run(_create_fixture())
    try:
        summary = run(
            get_metrics_summary(
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
            )
        )
        published, reach, anonymous, attempts, pass_rate = run(
            _direct_learning_totals()
        )

        assert summary.published_briefing_count == published
        assert summary.crew_reach == reach
        assert summary.anonymous_quiz_response_count == anonymous
        assert summary.first_attempt_count == attempts
        assert summary.first_attempt_pass_rate == pytest.approx(pass_rate)

        question_by_id = {
            question.question_id: question for question in summary.question_performance
        }
        assert question_by_id[question_one].first_attempt_count == 2
        assert question_by_id[question_one].first_attempt_correct_count == 1
        assert question_by_id[question_two].first_attempt_wrong_count == 2

        cluster = next(
            item
            for item in summary.repeat_hazards
            if item.category == category and item.location == location
        )
        assert cluster.report_count == 3
        assert cluster.recurrence_count == 2
        responsible = next(
            item
            for item in cluster.responsible_rework
            if item.profile_id == RESPONSIBLE_ID
        )
        assert responsible.rework_rate == pytest.approx(
            run(_responsible_rework_rate())
        )
    finally:
        run(_cleanup(report_ids))
