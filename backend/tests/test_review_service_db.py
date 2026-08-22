"""Prove review evidence and its transition commit or roll back together."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.api.reports import review_error
from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, ReportStatus, ReviewDecision, Role
from app.domain.transitions import TransitionError
from app.services.report_service import Actor, create_report, transition_report
from app.services import review_service as review_service_module
from app.services.review_service import ReviewError, review_report

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
RESPONSIBLE_ID = UUID("00000000-0000-0000-0000-000000000004")
_test_loop: asyncio.AbstractEventLoop | None = None
T = TypeVar("T")


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Share one pool per module and close it after all integration cases."""
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
    """Run each integration operation on the module's shared event loop."""
    assert _test_loop is not None
    return _test_loop.run_until_complete(coroutine)


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute(
            "delete from notifications where entity_type = 'report' and entity_id = $1",
            report_id,
        )
        await conn.execute("delete from reports where id = $1", report_id)


async def make_report() -> UUID:
    return await create_report(REPORTER_ID, f"review integration fixture {uuid4()}")


async def move_to_review(report_id: UUID) -> None:
    await transition_report(
        report_id,
        ReportStatus.SUBMITTED,
        Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
    )
    await transition_report(report_id, ReportStatus.AI_DRAFTED, Actor.system())
    await transition_report(report_id, ReportStatus.UNDER_REVIEW, Actor.system())


async def review_state(report_id: UUID) -> tuple[str, int, int, int, int]:
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            select
              r.status::text,
              (select count(*) from review_decisions where report_id = r.id),
              (select count(*) from report_assignments where report_id = r.id),
              (select count(*) from corrective_actions where report_id = r.id),
              (select count(*) from audit_log where report_id = r.id)
            from reports r
            where r.id = $1
            """,
            report_id,
        )
        assert row is not None
        return row[0], row[1], row[2], row[3], row[4]


def test_failed_transition_rolls_back_review_decision() -> None:
    report_id = run(make_report())
    try:
        with pytest.raises(TransitionError) as error:
            run(
                review_report(
                    report_id,
                    Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                    decision=ReviewDecision.REJECT,
                    target=ReportStatus.REJECTED,
                    reason="This report has not reached review.",
                )
            )

        assert error.value.code == "illegal_transition"
        assert run(review_state(report_id)) == ("draft", 0, 0, 0, 1)
    finally:
        run(cleanup(report_id))


def test_correction_without_reason_is_clean_422_and_rolls_back() -> None:
    report_id = run(make_report())
    try:
        run(move_to_review(report_id))
        with pytest.raises(ReviewError) as error:
            run(
                review_report(
                    report_id,
                    Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                    decision=ReviewDecision.REQUEST_INFO,
                    target=ReportStatus.INFO_REQUESTED,
                    reason="Confirm who was exposed.",
                    corrected_category="edge protection",
                )
            )

        assert error.value.code == "correction_reason_required"
        http_error = review_error(error.value)
        assert http_error.status_code == 422
        assert http_error.detail["code"] == "correction_reason_required"
        assert run(review_state(report_id)) == ("under_review", 0, 0, 0, 4)
    finally:
        run(cleanup(report_id))


def test_approval_creates_assignment_action_decision_and_transition() -> None:
    report_id = run(make_report())
    try:
        run(move_to_review(report_id))
        due_at = datetime.now(timezone.utc) + timedelta(days=3)
        result = run(
            review_report(
                report_id,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                decision=ReviewDecision.APPROVE,
                target=ReportStatus.ACTION_ASSIGNED,
                corrected_action="Install secured guardrails before work resumes.",
                correction_reason="Phase 1 requires the reviewer to define the action.",
                assignee_id=RESPONSIBLE_ID,
                due_at=due_at,
            )
        )

        assert result.report["status"] == "action_assigned"
        assert result.assignment_id is not None
        assert result.corrective_action_id is not None
        assert run(review_state(report_id)) == ("action_assigned", 1, 1, 1, 5)

        async def read_atomic_rows() -> tuple[object, str, UUID, datetime]:
            async with connection() as conn:
                return await conn.fetchrow(
                    """
                    select d.corrections, a.action_text, ra.assignee_id, ra.due_at
                    from review_decisions d
                    join reports r on r.id = d.report_id
                    join report_assignments ra on ra.report_id = r.id and ra.active
                    join corrective_actions a on a.assignment_id = ra.id
                    where r.id = $1
                    """,
                    report_id,
                )

        corrections, action_text, assignee_id, stored_due_at = run(read_atomic_rows())
        assert json.loads(corrections)["action"] == {
            "before": None,
            "after": "Install secured guardrails before work resumes.",
        }
        assert action_text == "Install secured guardrails before work resumes."
        assert assignee_id == RESPONSIBLE_ID
        assert stored_due_at == due_at

        async def read_notification() -> tuple[str, UUID]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select kind, recipient_id
                    from notifications
                    where entity_type = 'report' and entity_id = $1
                    """,
                    report_id,
                )
                assert row is not None
                return row["kind"], row["recipient_id"]

        assert run(read_notification()) == ("assigned", RESPONSIBLE_ID)
    finally:
        run(cleanup(report_id))


def test_assignment_rolls_back_when_notification_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id = run(make_report())
    try:
        run(move_to_review(report_id))

        async def fail_notification(*_: object, **__: object) -> None:
            raise RuntimeError("notification unavailable")

        monkeypatch.setattr(review_service_module, "send_notification", fail_notification)
        with pytest.raises(RuntimeError, match="notification unavailable"):
            run(
                review_report(
                    report_id,
                    Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                    decision=ReviewDecision.APPROVE,
                    target=ReportStatus.ACTION_ASSIGNED,
                    corrected_action="Install secured guardrails.",
                    correction_reason="Reviewer defined the Phase 1 action.",
                    assignee_id=RESPONSIBLE_ID,
                    due_at=datetime.now(timezone.utc) + timedelta(days=1),
                )
            )

        assert run(review_state(report_id)) == ("under_review", 0, 0, 0, 4)
    finally:
        run(cleanup(report_id))


def test_action_assigned_cannot_bypass_assignment_precondition() -> None:
    report_id = run(make_report())
    try:
        run(move_to_review(report_id))
        with pytest.raises(TransitionError) as error:
            run(
                transition_report(
                    report_id,
                    ReportStatus.ACTION_ASSIGNED,
                    Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                )
            )

        assert error.value.code == "assignment_required"
        assert run(review_state(report_id)) == ("under_review", 0, 0, 0, 4)
    finally:
        run(cleanup(report_id))
