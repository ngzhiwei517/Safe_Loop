"""Prove evidence, action state, report state, and audit commit together."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import datetime, timedelta, timezone
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, ReportStatus, ReviewDecision, Role
from app.domain.transitions import TransitionError
from app.services import action_service as action_service_module
from app.services.action_service import submit_action
from app.services.report_service import Actor, create_report, transition_report
from app.services.review_service import review_report

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
RESPONSIBLE_ID = UUID("00000000-0000-0000-0000-000000000004")
_test_loop: asyncio.AbstractEventLoop | None = None
T = TypeVar("T")


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
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


async def make_assigned_action() -> tuple[UUID, UUID, UUID]:
    report_id = await create_report(REPORTER_ID, f"action evidence fixture {uuid4()}")
    await transition_report(
        report_id,
        ReportStatus.SUBMITTED,
        Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
    )
    await transition_report(report_id, ReportStatus.AI_DRAFTED, Actor.system())
    await transition_report(report_id, ReportStatus.UNDER_REVIEW, Actor.system())
    result = await review_report(
        report_id,
        Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
        decision=ReviewDecision.APPROVE,
        target=ReportStatus.ACTION_ASSIGNED,
        corrected_action="Secure the guardrail before work resumes.",
        correction_reason="The approved action must be explicit.",
        assignee_id=RESPONSIBLE_ID,
        due_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    assert result.corrective_action_id is not None
    async with connection() as conn:
        media_id = await conn.fetchval(
            """
            insert into report_media (
              report_id, storage_path, mime_type, phase, caption
            )
            values ($1, $2, 'image/jpeg', 'evidence'::media_phase, null)
            returning id
            """,
            report_id,
            f"{RESPONSIBLE_ID}/{report_id}/{uuid4()}.jpg",
        )
    assert isinstance(media_id, UUID)
    return report_id, result.corrective_action_id, media_id


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute(
            "delete from notifications where entity_type = 'report' and entity_id = $1",
            report_id,
        )
        await conn.execute("delete from reports where id = $1", report_id)


async def submission_state(
    report_id: UUID,
    action_id: UUID,
    media_id: UUID,
) -> tuple[str, str, str | None, UUID | None, int]:
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            select
              report.status::text,
              action.status::text,
              action.completed_note,
              media.corrective_action_id,
              (select count(*) from audit_log where report_id = report.id)
            from reports report
            join corrective_actions action on action.id = $2
            join report_media media on media.id = $3
            where report.id = $1
            """,
            report_id,
            action_id,
            media_id,
        )
        assert row is not None
        return row[0], row[1], row[2], row[3], row[4]


def test_submission_links_proof_and_appends_one_transition_audit() -> None:
    report_id, action_id, media_id = run(make_assigned_action())
    try:
        before = run(submission_state(report_id, action_id, media_id))
        result = run(
            submit_action(
                report_id,
                action_id,
                Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE),
                completed_note="Guardrail anchors tightened and checked.",
                media_ids=[media_id],
            )
        )

        assert result.report["status"] == "action_submitted"
        after = run(submission_state(report_id, action_id, media_id))
        assert after[:4] == (
            "action_submitted",
            "submitted",
            "Guardrail anchors tightened and checked.",
            action_id,
        )
        assert after[4] == before[4] + 1
    finally:
        run(cleanup(report_id))


def test_transition_failure_rolls_back_action_and_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id, action_id, media_id = run(make_assigned_action())

    async def fail_transition(*_: object, **__: object) -> None:
        raise TransitionError("illegal_transition", "forced test failure")

    monkeypatch.setattr(action_service_module, "transition_report", fail_transition)
    try:
        before = run(submission_state(report_id, action_id, media_id))
        with pytest.raises(TransitionError):
            run(
                submit_action(
                    report_id,
                    action_id,
                    Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE),
                    completed_note=None,
                    media_ids=[media_id],
                )
            )
        assert run(submission_state(report_id, action_id, media_id)) == before
    finally:
        run(cleanup(report_id))
