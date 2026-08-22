"""Prove urgent alerts and notifications keep their transactional promises."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import timedelta
import json
import os
from typing import Any, TypeVar
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, Role
from app.services.alert_service import (
    acknowledge_alert,
    escalate_due_alerts,
    get_alert,
    list_alerts,
    raise_alert,
    resolve_alert,
)
from app.services.notification_service import list_notifications, mark_notification_read
from app.services.report_service import Actor, create_report

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000006")
_test_loop: asyncio.AbstractEventLoop | None = None
T = TypeVar("T")


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Share one bounded pool so the remote test database cannot exhaust connections."""
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
    """Run all operations on the module's single event loop."""
    assert _test_loop is not None
    return _test_loop.run_until_complete(coroutine)


def reporter() -> Actor:
    return Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER)


def reviewer() -> Actor:
    return Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        alert_ids = await conn.fetch(
            "select id from alerts where report_id = $1",
            report_id,
        )
        ids = [row["id"] for row in alert_ids]
        if ids:
            await conn.execute(
                "delete from notifications where entity_type = 'alert' and entity_id = any($1::uuid[])",
                ids,
            )
        await conn.execute(
            "delete from notifications where entity_type = 'report' and entity_id = $1",
            report_id,
        )
        await conn.execute("delete from reports where id = $1", report_id)


async def make_alert() -> tuple[UUID, asyncpg.Record]:
    report_id = await create_report(
        REPORTER_ID,
        f"urgent integration fixture {uuid4()}",
        location_text="Level 14, Block C",
    )
    return report_id, await raise_alert(report_id, reporter(), location_text="Level 14, Block C")


def test_alert_exists_on_an_unsubmitted_draft_and_is_audited() -> None:
    report_id, alert = run(make_alert())
    try:
        async def inspect() -> tuple[str, str, list[str], int]:
            async with connection() as conn:
                report = await conn.fetchrow(
                    "select status::text, urgency::text from reports where id = $1",
                    report_id,
                )
                recipients = await conn.fetch(
                    """
                    select recipient_id
                    from notifications
                    where kind = 'alert_raised' and entity_id = $1
                    """,
                    alert["id"],
                )
                audits = await conn.fetchval(
                    "select count(*) from audit_log where report_id = $1 and event = 'raise_alert'",
                    report_id,
                )
                assert report is not None
                return report["status"], report["urgency"], [str(row["recipient_id"]) for row in recipients], audits

        status, urgency, recipients, audits = run(inspect())
        assert status == "draft"
        assert urgency == "critical"
        assert str(REVIEWER_ID) in recipients
        assert audits == 1

        visible = run(list_alerts(reviewer()))
        assert any(row["id"] == alert["id"] for row in visible)
    finally:
        run(cleanup(report_id))


def test_acknowledged_identity_is_absent_until_the_deliberate_act() -> None:
    report_id, created = run(make_alert())
    try:
        before = run(get_alert(created["id"], reporter()))
        assert before["acknowledged_at"] is None
        assert before["acknowledged_by_name"] is None

        after = run(acknowledge_alert(created["id"], reviewer()))
        assert after["acknowledged_at"] is not None
        assert after["acknowledged_by"] == REVIEWER_ID
        assert after["acknowledged_by_name"] == "Lim Wei Sheng"

        async def audit_count() -> int:
            async with connection() as conn:
                return await conn.fetchval(
                    "select count(*) from audit_log where report_id = $1 and event = 'acknowledge_alert'",
                    report_id,
                )

        assert run(audit_count()) == 1
    finally:
        run(cleanup(report_id))


def test_escalation_fires_at_threshold_once_and_notifies_wider_group() -> None:
    report_id, alert = run(make_alert())
    try:
        assert run(
            escalate_due_alerts(
                threshold_minutes=5,
                now=alert["raised_at"] + timedelta(minutes=5) - timedelta(microseconds=1),
            )
        ) == []

        escalated = run(
            escalate_due_alerts(
                threshold_minutes=5,
                now=alert["raised_at"] + timedelta(minutes=5),
            )
        )
        assert escalated == [alert["id"]]
        assert run(
            escalate_due_alerts(
                threshold_minutes=5,
                now=alert["raised_at"] + timedelta(minutes=10),
            )
        ) == []

        async def inspect() -> tuple[object, set[UUID], int]:
            async with connection() as conn:
                row = await conn.fetchrow("select escalated_at from alerts where id = $1", alert["id"])
                notifications = await conn.fetch(
                    """
                    select recipient_id, payload
                    from notifications
                    where entity_id = $1 and kind = 'alert_raised'
                    """,
                    alert["id"],
                )
                escalation_recipients = {
                    item["recipient_id"]
                    for item in notifications
                    if json.loads(item["payload"])["escalation_level"] == 1
                }
                audits = await conn.fetchval(
                    "select count(*) from audit_log where report_id = $1 and event = 'escalate_alert'",
                    report_id,
                )
                assert row is not None
                return row["escalated_at"], escalation_recipients, audits

        escalated_at, recipients, audits = run(inspect())
        assert escalated_at is not None
        assert {REVIEWER_ID, ADMIN_ID}.issubset(recipients)
        assert audits == 1
    finally:
        run(cleanup(report_id))


def test_notifications_stay_unread_until_explicitly_opened() -> None:
    report_id, alert = run(make_alert())
    try:
        items, unread_before, _ = run(list_notifications(reviewer(), limit=100))
        notification = next(item for item in items if item["entity_id"] == alert["id"])
        assert notification["read_at"] is None

        marked = run(mark_notification_read(notification["id"], reviewer()))
        assert marked["read_at"] is not None
        _, unread_after, _ = run(list_notifications(reviewer(), limit=100))
        assert unread_after == unread_before - 1
    finally:
        run(cleanup(report_id))


def test_resolution_is_audited_and_cannot_be_blank() -> None:
    report_id, alert = run(make_alert())
    try:
        from app.services.alert_service import AlertError

        with pytest.raises(AlertError) as error:
            run(resolve_alert(alert["id"], reviewer(), resolution_note="  "))
        assert error.value.code == "alert_resolution_required"

        resolved = run(
            resolve_alert(
                alert["id"],
                reviewer(),
                resolution_note="Area isolated and edge protection installed.",
            )
        )
        assert resolved["resolution_note"] == "Area isolated and edge protection installed."
        assert resolved["acknowledged_by"] == REVIEWER_ID

        async def audit_count() -> int:
            async with connection() as conn:
                return await conn.fetchval(
                    "select count(*) from audit_log where report_id = $1 and event = 'resolve_alert'",
                    report_id,
                )

        assert run(audit_count()) == 1
    finally:
        run(cleanup(report_id))


def test_database_rejects_sentence_payloads() -> None:
    async def exercise() -> None:
        async with connection() as conn:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    """
                    insert into notifications (
                      recipient_id, kind, entity_type, entity_id, payload
                    )
                    values ($1, 'assigned', 'report', $2, $3::jsonb)
                    """,
                    REVIEWER_ID,
                    uuid4(),
                    json.dumps({"message": "go to level 14"}),
                )

    run(exercise())
