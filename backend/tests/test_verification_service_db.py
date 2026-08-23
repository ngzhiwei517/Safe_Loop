"""Prove every verification cycle, transition, and notification is atomic."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import datetime, timedelta, timezone
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, ReportStatus, ReviewDecision, Role
from app.domain.transitions import TransitionError
from app.services import verification_service as verification_service_module
from app.services.action_service import submit_action
from app.services.media_service import assert_report_readable
from app.services.report_service import (
    Actor,
    create_report,
    get_report,
    get_timeline,
    transition_report,
)
from app.services.review_service import review_report
from app.services.verification_service import VerificationError, verify_report

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


async def make_submitted_action(
    *,
    is_confidential: bool = False,
    include_original_photo: bool = False,
    include_evidence_photo: bool = False,
) -> tuple[UUID, UUID, UUID, datetime]:
    report_id = await create_report(
        REPORTER_ID,
        f"verification fixture {uuid4()}",
        is_confidential=is_confidential,
    )
    reporter = Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER)
    reviewer = Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
    await transition_report(report_id, ReportStatus.SUBMITTED, reporter)
    await transition_report(report_id, ReportStatus.AI_DRAFTED, Actor.system())
    await transition_report(report_id, ReportStatus.UNDER_REVIEW, Actor.system())
    due_at = datetime.now(timezone.utc) + timedelta(days=2)
    reviewed = await review_report(
        report_id,
        reviewer,
        decision=ReviewDecision.APPROVE,
        target=ReportStatus.ACTION_ASSIGNED,
        corrected_action="Secure every guardrail anchor before work resumes.",
        correction_reason="The approved action must be explicit.",
        assignee_id=RESPONSIBLE_ID,
        due_at=due_at,
    )
    assert reviewed.corrective_action_id is not None
    assert reviewed.assignment_id is not None
    evidence_media_ids: list[UUID] = []
    if include_original_photo or include_evidence_photo:
        async with connection() as conn:
            if include_original_photo:
                await conn.execute(
                    """
                    insert into report_media (
                      report_id, storage_path, mime_type, phase, caption
                    )
                    values ($1, $2, 'image/jpeg', 'original', 'Original condition')
                    """,
                    report_id,
                    f"{REPORTER_ID}/{report_id}/original.jpg",
                )
            if include_evidence_photo:
                evidence_media_id = await conn.fetchval(
                    """
                    insert into report_media (
                      report_id, storage_path, mime_type, phase, caption
                    )
                    values ($1, $2, 'image/jpeg', 'evidence', 'Completed work')
                    returning id
                    """,
                    report_id,
                    f"{RESPONSIBLE_ID}/{report_id}/evidence.jpg",
                )
                assert isinstance(evidence_media_id, UUID)
                evidence_media_ids.append(evidence_media_id)
    await submit_action(
        report_id,
        reviewed.corrective_action_id,
        Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE),
        completed_note="Tightened the upper and lower anchors.",
        media_ids=evidence_media_ids,
    )
    return report_id, reviewed.corrective_action_id, reviewed.assignment_id, due_at


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute(
            "delete from notifications where entity_type = 'report' and entity_id = $1",
            report_id,
        )
        await conn.execute("delete from reports where id = $1", report_id)


async def read_cycle_state(report_id: UUID, action_id: UUID) -> asyncpg.Record:
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            select
              report.status::text as report_status,
              report.closed_at,
              action.status::text as action_status,
              action.rework_count,
              action.due_at as action_due_at,
              assignment.id as assignment_id,
              assignment.assignee_id,
              assignment.active,
              assignment.due_at as assignment_due_at,
              (select count(*) from verifications where report_id = report.id) as verification_count,
              (select count(*) from audit_log
               where report_id = report.id and event = 'verify_and_close') as closure_count
            from reports report
            join corrective_actions action on action.id = $2
            join report_assignments assignment on assignment.id = action.assignment_id
            where report.id = $1
            """,
            report_id,
            action_id,
        )
        assert row is not None
        return row


async def read_closure_delivery(report_id: UUID) -> asyncpg.Record:
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            select
              receipt.*,
              report.is_confidential,
              (
                select count(*)
                from notifications notification
                where notification.entity_type = 'report'
                  and notification.entity_id = receipt.report_id
                  and notification.kind = 'report_closed'
              ) as notification_count,
              (
                select notification.recipient_id
                from notifications notification
                where notification.entity_type = 'report'
                  and notification.entity_id = receipt.report_id
                  and notification.kind = 'report_closed'
                order by notification.created_at, notification.id
                limit 1
              ) as notification_recipient
            from closure_receipts receipt
            join reports report on report.id = receipt.report_id
            where receipt.report_id = $1
            """,
            report_id,
        )
        assert row is not None
        return row


def test_failed_verification_preserves_assignment_and_increments_rework() -> None:
    report_id, action_id, assignment_id, _ = run(make_submitted_action())
    new_due_at = datetime.now(timezone.utc) + timedelta(days=4)
    try:
        result = run(
            verify_report(
                report_id,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                passed=False,
                checklist={"hazard_removed": False},
                notes="The lower anchor was pull-tested.",
                reason="The lower anchor still moves when pulled.",
                new_due_at=new_due_at,
            )
        )

        state = run(read_cycle_state(report_id, action_id))
        assert result.report["status"] == "action_assigned"
        assert state["report_status"] == "action_assigned"
        assert state["action_status"] == "assigned"
        assert state["rework_count"] == 1
        assert state["assignment_id"] == assignment_id
        assert state["assignee_id"] == RESPONSIBLE_ID
        assert state["active"] is True
        assert state["action_due_at"] == new_due_at
        assert state["assignment_due_at"] == new_due_at
        assert state["verification_count"] == 1

        async def read_notification() -> tuple[str, UUID]:
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select kind, recipient_id from notifications
                    where entity_type = 'report' and entity_id = $1 and kind = 'sent_back'
                    """,
                    report_id,
                )
                assert row is not None
                return row["kind"], row["recipient_id"]

        assert run(read_notification()) == ("sent_back", RESPONSIBLE_ID)
    finally:
        run(cleanup(report_id))


def test_transition_failure_rolls_back_the_verification_and_rework(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id, action_id, _, _ = run(make_submitted_action())

    async def fail_transition(*_: object, **__: object) -> None:
        raise TransitionError("illegal_transition", "forced transition failure")

    monkeypatch.setattr(
        verification_service_module,
        "transition_report",
        fail_transition,
    )
    try:
        before = run(read_cycle_state(report_id, action_id))
        with pytest.raises(TransitionError):
            run(
                verify_report(
                    report_id,
                    Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                    passed=False,
                    checklist=None,
                    notes="The lower anchor was inspected.",
                    reason="The lower anchor still moves when pulled.",
                    new_due_at=datetime.now(timezone.utc) + timedelta(days=4),
                )
            )
        after = run(read_cycle_state(report_id, action_id))
        assert tuple(after) == tuple(before)
    finally:
        run(cleanup(report_id))


def test_transition_failure_rolls_back_receipt_and_closure_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_id, action_id, _, _ = run(make_submitted_action())

    async def fail_transition(*_: object, **__: object) -> None:
        raise TransitionError("illegal_transition", "forced transition failure")

    async def read_delivery_counts() -> tuple[int, int]:
        async with connection() as conn:
            row = await conn.fetchrow(
                """
                select
                  (select count(*) from closure_receipts where report_id = $1)::integer
                    as receipt_count,
                  (
                    select count(*)
                    from notifications
                    where entity_type = 'report'
                      and entity_id = $1
                      and kind = 'report_closed'
                  )::integer as notification_count
                """,
                report_id,
            )
            assert row is not None
            return row["receipt_count"], row["notification_count"]

    monkeypatch.setattr(
        verification_service_module,
        "transition_report",
        fail_transition,
    )
    try:
        before = run(read_cycle_state(report_id, action_id))
        with pytest.raises(TransitionError):
            run(
                verify_report(
                    report_id,
                    Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                    passed=True,
                    checklist={"hazard_removed": True},
                    notes="Both anchors held during the final pull test.",
                )
            )
        after = run(read_cycle_state(report_id, action_id))
        assert tuple(after) == tuple(before)
        assert run(read_delivery_counts()) == (0, 0)
    finally:
        run(cleanup(report_id))


def test_two_failures_then_pass_preserves_three_cycles_and_closes_once() -> None:
    report_id, action_id, _, _ = run(make_submitted_action())
    reviewer = Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
    responsible = Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE)
    try:
        for cycle in range(2):
            run(
                verify_report(
                    report_id,
                    reviewer,
                    passed=False,
                    checklist={"hazard_removed": False},
                    notes=f"Inspection cycle {cycle + 1} completed.",
                    reason=f"Anchor {cycle + 1} still moves under load.",
                    new_due_at=datetime.now(timezone.utc) + timedelta(days=cycle + 3),
                )
            )
            run(
                submit_action(
                    report_id,
                    action_id,
                    responsible,
                    completed_note=f"Reworked anchor after cycle {cycle + 1}.",
                    media_ids=[],
                )
            )

        result = run(
            verify_report(
                report_id,
                reviewer,
                passed=True,
                checklist={
                    "hazard_removed": True,
                    "same_location": True,
                    "no_new_hazard": True,
                },
                notes="All anchors passed the final pull test.",
            )
        )
        state = run(read_cycle_state(report_id, action_id))
        assert result.report["status"] == "verified_closed"
        assert state["report_status"] == "verified_closed"
        assert state["action_status"] == "verified"
        assert state["rework_count"] == 2
        assert state["verification_count"] == 3
        assert state["closure_count"] == 1
        assert state["closed_at"] is not None

        timeline = run(get_timeline(report_id))
        verification_events = [
            row["event"]
            for row in timeline
            if row["event"] in {"submit_evidence", "verification_failed", "verify_and_close"}
        ]
        assert verification_events == [
            "submit_evidence",
            "verification_failed",
            "submit_evidence",
            "verification_failed",
            "submit_evidence",
            "verify_and_close",
        ]
        failed_reasons = [
            row["reason"] for row in timeline if row["event"] == "verification_failed"
        ]
        assert failed_reasons == [
            "Anchor 1 still moves under load.",
            "Anchor 2 still moves under load.",
        ]

        closed_at = state["closed_at"]
        with pytest.raises(VerificationError) as error:
            run(
                verify_report(
                    report_id,
                    reviewer,
                    passed=True,
                    checklist=None,
                    notes="Duplicate close attempt.",
                )
            )
        assert error.value.code == "verification_not_ready"
        assert run(read_cycle_state(report_id, action_id))["closed_at"] == closed_at

        async def overwrite_closed_at() -> None:
            async with connection() as conn:
                await conn.execute(
                    "update reports set closed_at = closed_at + interval '1 second' where id = $1",
                    report_id,
                )

        with pytest.raises(asyncpg.InsufficientPrivilegeError) as database_error:
            run(overwrite_closed_at())
        assert database_error.value.sqlstate == "42501"
        assert run(read_cycle_state(report_id, action_id))["closed_at"] == closed_at
    finally:
        run(cleanup(report_id))


def test_closure_delivers_exactly_one_receipt_to_confidential_reporter() -> None:
    report_id, _, _, _ = run(make_submitted_action(is_confidential=True))
    try:
        run(
            verify_report(
                report_id,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                passed=True,
                checklist={"hazard_removed": True},
                notes="Both anchors held during the final pull test.",
            )
        )

        delivery = run(read_closure_delivery(report_id))
        assert delivery["is_confidential"] is True
        assert delivery["reporter_id"] == REPORTER_ID
        assert delivery["reporter_locale"] == "en"
        assert delivery["verified_by_id"] == REVIEWER_ID
        assert delivery["notification_count"] == 1
        assert delivery["notification_recipient"] == REPORTER_ID

        report = run(get_report(report_id))
        assert report is not None
        assert_report_readable(
            report,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
    finally:
        run(cleanup(report_id))


def test_receipt_omits_pair_when_final_submission_has_no_evidence_photo() -> None:
    report_id, _, _, _ = run(
        make_submitted_action(include_original_photo=True)
    )
    try:
        run(
            verify_report(
                report_id,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                passed=True,
                checklist={"hazard_removed": True},
                notes="The repaired anchors passed inspection.",
            )
        )

        delivery = run(read_closure_delivery(report_id))
        assert delivery["before_media_id"] is None
        assert delivery["after_media_id"] is None
    finally:
        run(cleanup(report_id))


def test_receipt_snapshots_original_and_final_evidence_photo_pair() -> None:
    report_id, _, _, _ = run(
        make_submitted_action(
            include_original_photo=True,
            include_evidence_photo=True,
        )
    )
    try:
        run(
            verify_report(
                report_id,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                passed=True,
                checklist={"hazard_removed": True},
                notes="The repaired anchors passed inspection.",
            )
        )

        delivery = run(read_closure_delivery(report_id))
        assert isinstance(delivery["before_media_id"], UUID)
        assert isinstance(delivery["after_media_id"], UUID)
    finally:
        run(cleanup(report_id))


@pytest.mark.parametrize("actor", [Actor.ai(), Actor.system()])
def test_machine_closure_is_refused_by_service_and_leaves_no_verification(
    actor: Actor,
) -> None:
    report_id, action_id, _, _ = run(make_submitted_action())
    try:
        with pytest.raises(VerificationError) as error:
            run(
                verify_report(
                    report_id,
                    actor,
                    passed=True,
                    checklist=None,
                    notes="Machine close attempt.",
                )
            )
        assert error.value.code == "verification_actor_forbidden"
        state = run(read_cycle_state(report_id, action_id))
        assert state["report_status"] == "action_submitted"
        assert state["verification_count"] == 0
    finally:
        run(cleanup(report_id))


@pytest.mark.parametrize("actor_type", ["ai", "system"])
def test_raw_sql_machine_closure_is_refused_by_database(actor_type: str) -> None:
    report_id, action_id, _, _ = run(make_submitted_action())

    async def raw_close() -> None:
        async with connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "select set_config('safeloop.actor_type', $1, true)",
                    actor_type,
                )
                await conn.execute(
                    "update reports set status = 'verified_closed'::report_status where id = $1",
                    report_id,
                )

    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError) as error:
            run(raw_close())
        assert error.value.sqlstate == "42501"
        assert run(read_cycle_state(report_id, action_id))["report_status"] == "action_submitted"
    finally:
        run(cleanup(report_id))


def test_blank_failure_reason_changes_nothing() -> None:
    report_id, action_id, _, _ = run(make_submitted_action())
    try:
        before = run(read_cycle_state(report_id, action_id))
        with pytest.raises(VerificationError) as error:
            run(
                verify_report(
                    report_id,
                    Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                    passed=False,
                    checklist=None,
                    notes="Evidence inspected.",
                    reason="   ",
                    new_due_at=datetime.now(timezone.utc) + timedelta(days=2),
                )
            )
        assert error.value.code == "verification_reason_required"
        after = run(read_cycle_state(report_id, action_id))
        assert tuple(after) == tuple(before)
    finally:
        run(cleanup(report_id))
