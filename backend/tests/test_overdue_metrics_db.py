"""Reconcile daily reminders and dashboard metrics against real Postgres rows."""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
import json
import os
from statistics import median
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, Role
from app.services.metrics_service import OPEN_REPORT_STATUSES, get_metrics_summary
from app.services.notification_service import list_notifications, mark_notification_read
from app.services.overdue_service import send_daily_overdue_notifications
from app.services.report_service import Actor

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
RESPONSIBLE_ID = UUID("00000000-0000-0000-0000-000000000004")
_test_loop: asyncio.AbstractEventLoop | None = None


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Share one pool while keeping each fixture explicitly removable."""
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


async def cleanup_reports(report_ids: list[UUID]) -> None:
    async with connection() as conn:
        await conn.execute(
            """
            delete from notifications
            where entity_id = any($1::uuid[])
               or payload ->> 'report_id' = any($2::text[])
            """,
            report_ids,
            [str(report_id) for report_id in report_ids],
        )
        await conn.execute("delete from reports where id = any($1::uuid[])", report_ids)


async def insert_report(
    conn: asyncpg.pool.PoolConnectionProxy[asyncpg.Record],
    *,
    report_id: UUID,
    status: str,
    submitted_at: datetime,
    closed_at: datetime | None = None,
) -> None:
    await conn.execute(
        """
        insert into reports (
          id, reporter_id, status, description_original, submitted_at,
          closed_at, created_at, updated_at
        )
        values ($1, $2, $3::report_status, $4, $5, $6, $5, $5)
        """,
        report_id,
        REPORTER_ID,
        status,
        f"metric fixture {report_id}",
        submitted_at,
        closed_at,
    )


async def insert_action(
    conn: asyncpg.pool.PoolConnectionProxy[asyncpg.Record],
    *,
    report_id: UUID,
    status: str,
    rework_count: int,
    due_at: datetime,
) -> UUID:
    assignment_id = await conn.fetchval(
        """
        insert into report_assignments (
          report_id, assignee_id, case_role, due_at
        )
        values ($1, $2, 'responsible'::case_role, $3)
        returning id
        """,
        report_id,
        RESPONSIBLE_ID,
        due_at,
    )
    action_id = await conn.fetchval(
        """
        insert into corrective_actions (
          report_id, assignment_id, action_text, status, rework_count, due_at
        )
        values ($1, $2, 'Secure the hazard.', $3::action_status, $4, $5)
        returning id
        """,
        report_id,
        assignment_id,
        status,
        rework_count,
        due_at,
    )
    assert isinstance(action_id, UUID)
    return action_id


async def add_event(
    conn: asyncpg.pool.PoolConnectionProxy[asyncpg.Record],
    report_id: UUID,
    target: str,
    created_at: datetime,
) -> None:
    await conn.execute(
        """
        insert into audit_log (
          report_id, actor_type, actor_id, event, target, created_at
        )
        values ($1, 'human'::actor_type, $2, $3, $4::report_status, $5)
        """,
        report_id,
        REVIEWER_ID,
        f"fixture_{target}",
        target,
        created_at,
    )


async def create_metric_fixture() -> list[UUID]:
    report_ids = [uuid4() for _ in range(5)]
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with connection() as conn:
        async with conn.transaction():
            await insert_report(
                conn,
                report_id=report_ids[0],
                status="verified_closed",
                submitted_at=base,
                closed_at=base + timedelta(hours=10),
            )
            await insert_report(
                conn,
                report_id=report_ids[1],
                status="verified_closed",
                submitted_at=base,
                closed_at=base + timedelta(hours=9),
            )
            await insert_report(
                conn,
                report_id=report_ids[2],
                status="action_assigned",
                submitted_at=base,
            )
            await insert_report(
                conn,
                report_id=report_ids[3],
                status="action_assigned",
                submitted_at=base,
            )
            await insert_report(
                conn,
                report_id=report_ids[4],
                status="under_review",
                submitted_at=base,
            )

            review_offsets = [2, 4, 6, 8, 10]
            assignment_offsets = [1, 3, 5, 7]
            for index, minutes in enumerate(review_offsets):
                await add_event(
                    conn,
                    report_ids[index],
                    "under_review",
                    base + timedelta(minutes=minutes),
                )
            for index, hours in enumerate(assignment_offsets):
                await add_event(
                    conn,
                    report_ids[index],
                    "action_assigned",
                    base + timedelta(hours=hours),
                )

            action_ids = [
                await insert_action(
                    conn,
                    report_id=report_ids[0],
                    status="verified",
                    rework_count=2,
                    due_at=base + timedelta(days=1),
                ),
                await insert_action(
                    conn,
                    report_id=report_ids[1],
                    status="verified",
                    rework_count=0,
                    due_at=base + timedelta(days=1),
                ),
                await insert_action(
                    conn,
                    report_id=report_ids[2],
                    status="assigned",
                    rework_count=1,
                    due_at=datetime.now(timezone.utc) - timedelta(days=1),
                ),
                await insert_action(
                    conn,
                    report_id=report_ids[3],
                    status="assigned",
                    rework_count=0,
                    due_at=datetime.now(timezone.utc) + timedelta(days=1),
                ),
            ]

            for cycle in range(3):
                passed = cycle == 2
                await conn.execute(
                    """
                    insert into verifications (
                      report_id, corrective_action_id, reviewer_id, passed,
                      notes, reason, new_due_at, created_at
                    )
                    values ($1, $2, $3, $4, 'Fixture check', $5, $6, $7)
                    """,
                    report_ids[0],
                    action_ids[0],
                    REVIEWER_ID,
                    passed,
                    None if passed else f"Fixture deficiency {cycle}",
                    None if passed else base + timedelta(days=cycle + 2),
                    base + timedelta(hours=cycle + 2),
                )
            await conn.execute(
                """
                insert into verifications (
                  report_id, corrective_action_id, reviewer_id, passed,
                  notes, created_at
                )
                values ($1, $2, $3, true, 'Fixture check', $4)
                """,
                report_ids[1],
                action_ids[1],
                REVIEWER_ID,
                base + timedelta(hours=8),
            )
            await conn.execute(
                """
                insert into review_decisions (
                  report_id, reviewer_id, decision, corrections, correction_reason
                )
                values
                  ($1, $3, 'approve'::review_decision, $4::jsonb, 'Clarified action'),
                  ($2, $3, 'approve'::review_decision, null, null)
                """,
                report_ids[0],
                report_ids[1],
                REVIEWER_ID,
                json.dumps({"action": {"before": "Secure", "after": "Secure all"}}),
            )
    return report_ids


async def hand_calculated_summary() -> dict[str, object]:
    open_statuses = {status.value for status in OPEN_REPORT_STATUSES}
    async with connection() as conn:
        reports = await conn.fetch("select id, status::text, submitted_at, closed_at from reports")
        actions = await conn.fetch(
            """
            select
              action.report_id, action.status::text, action.rework_count,
              action.due_at, assignment.active, report.status::text as report_status
            from corrective_actions action
            join report_assignments assignment on assignment.id = action.assignment_id
            join reports report on report.id = action.report_id
            """
        )
        verifications = await conn.fetch("select report_id from verifications")
        events = await conn.fetch(
            """
            select report_id, target::text as target, created_at
            from audit_log
            where target in (
              'under_review'::report_status,
              'action_assigned'::report_status
            )
            """
        )
        reviews = await conn.fetch("select report_id, corrections from review_decisions")

    open_counts = {status: 0 for status in open_statuses}
    report_by_id = {row["id"]: row for row in reports}
    for report in reports:
        if report["status"] in open_counts:
            open_counts[report["status"]] += 1

    overdue_count = sum(
        action["status"] == "assigned"
        and action["active"]
        and action["report_status"] == "action_assigned"
        and action["due_at"] < datetime.now(timezone.utc)
        for action in actions
    )
    rework_rate = (
        sum(action["rework_count"] >= 1 for action in actions) / len(actions)
        if actions
        else 0.0
    )
    cycles = Counter(row["report_id"] for row in verifications)
    closed_cycles = [
        count
        for report_id, count in cycles.items()
        if report_by_id[report_id]["closed_at"] is not None
    ]

    event_times: dict[UUID, dict[str, datetime]] = defaultdict(dict)
    for event in events:
        current = event_times[event["report_id"]].get(event["target"])
        if current is None or event["created_at"] < current:
            event_times[event["report_id"]][event["target"]] = event["created_at"]

    def durations(start: str, end: str) -> list[float]:
        values: list[float] = []
        for report in reports:
            start_time = (
                report["submitted_at"]
                if start == "submitted"
                else event_times[report["id"]].get(start)
            )
            end_time = (
                report["closed_at"]
                if end == "verified_closed"
                else event_times[report["id"]].get(end)
            )
            if start_time is not None and end_time is not None:
                values.append((end_time - start_time).total_seconds())
        return values

    corrections: dict[UUID, bool] = defaultdict(bool)
    for review in reviews:
        corrections[review["report_id"]] = corrections[review["report_id"]] or (
            review["corrections"] is not None
            and review["corrections"] not in ({}, "{}")
        )
    return {
        "open_by_status": open_counts,
        "overdue_count": overdue_count,
        "rework_rate": rework_rate,
        "median_verification_cycles_to_close": (
            median(closed_cycles) if closed_cycles else None
        ),
        "median_submitted_to_under_review_seconds": (
            median(values) if (values := durations("submitted", "under_review")) else None
        ),
        "median_submitted_to_action_assigned_seconds": (
            median(values) if (values := durations("submitted", "action_assigned")) else None
        ),
        "median_action_assigned_to_verified_closed_seconds": (
            median(values)
            if (values := durations("action_assigned", "verified_closed"))
            else None
        ),
        "reviewer_correction_rate": (
            sum(corrections.values()) / len(corrections) if corrections else 0.0
        ),
    }


def test_metrics_match_independently_calculated_database_values() -> None:
    report_ids = run(create_metric_fixture())
    try:
        actual = run(
            get_metrics_summary(
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
            )
        )
        expected = run(hand_calculated_summary())

        assert actual.open_by_status == expected["open_by_status"]
        assert actual.overdue_count == expected["overdue_count"]
        assert actual.rework_rate == pytest.approx(expected["rework_rate"])
        assert actual.median_verification_cycles_to_close == pytest.approx(
            expected["median_verification_cycles_to_close"]
        )
        assert actual.median_submitted_to_under_review_seconds == pytest.approx(
            expected["median_submitted_to_under_review_seconds"]
        )
        assert actual.median_submitted_to_action_assigned_seconds == pytest.approx(
            expected["median_submitted_to_action_assigned_seconds"]
        )
        assert actual.median_action_assigned_to_verified_closed_seconds == pytest.approx(
            expected["median_action_assigned_to_verified_closed_seconds"]
        )
        assert actual.reviewer_correction_rate == pytest.approx(
            expected["reviewer_correction_rate"]
        )
    finally:
        run(cleanup_reports(report_ids))


async def create_overdue_rework_fixture() -> tuple[UUID, UUID, UUID]:
    report_id = uuid4()
    now = datetime.now(timezone.utc)
    async with connection() as conn:
        async with conn.transaction():
            await insert_report(
                conn,
                report_id=report_id,
                status="action_assigned",
                submitted_at=now - timedelta(days=2),
            )
            action_id = await insert_action(
                conn,
                report_id=report_id,
                status="assigned",
                rework_count=1,
                due_at=now - timedelta(days=1),
            )
            notification_id = await conn.fetchval(
                """
                insert into notifications (
                  recipient_id, kind, entity_type, entity_id, payload
                )
                values ($1, 'sent_back', 'report', $2, $3::jsonb)
                returning id
                """,
                RESPONSIBLE_ID,
                report_id,
                json.dumps({"report_id": str(report_id), "corrective_action_id": str(action_id)}),
            )
    assert isinstance(notification_id, UUID)
    return report_id, action_id, notification_id


def test_overdue_repeats_daily_and_sent_back_clears_only_on_resubmit() -> None:
    report_id, action_id, notification_id = run(create_overdue_rework_fixture())
    actor = Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE)
    today = date(2026, 8, 23)
    try:
        run(
            send_daily_overdue_notifications(
                as_of=datetime(2026, 8, 23, 0, 0, tzinfo=timezone.utc),
                delivery_date=today,
            )
        )
        run(
            send_daily_overdue_notifications(
                as_of=datetime(2026, 8, 23, 1, 0, tzinfo=timezone.utc),
                delivery_date=today,
            )
        )
        run(
            send_daily_overdue_notifications(
                as_of=datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc),
                delivery_date=today + timedelta(days=1),
            )
        )

        async def reminder_dates() -> list[date]:
            async with connection() as conn:
                return await conn.fetch(
                    """
                    select delivery_date
                    from notifications
                    where kind = 'overdue'
                      and entity_type = 'corrective_action'
                      and entity_id = $1
                    order by delivery_date
                    """,
                    action_id,
                )

        rows = run(reminder_dates())
        assert [row["delivery_date"] for row in rows] == [
            today,
            today + timedelta(days=1),
        ]

        _, _, _, unresolved_before = run(list_notifications(actor, limit=100))
        run(mark_notification_read(notification_id, actor))
        _, _, _, unresolved_after_read = run(list_notifications(actor, limit=100))
        assert unresolved_after_read == unresolved_before

        async def mark_resubmitted() -> None:
            async with connection() as conn:
                await conn.execute(
                    """
                    update corrective_actions
                    set status = 'submitted'::action_status
                    where id = $1
                    """,
                    action_id,
                )

        run(mark_resubmitted())
        _, _, _, unresolved_after_submit = run(list_notifications(actor, limit=100))
        assert unresolved_after_submit == unresolved_before - 1
    finally:
        run(cleanup_reports([report_id]))
