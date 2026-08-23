"""Prove daily reminders reuse the notification writer and carry only data."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import AsyncIterator
from uuid import UUID

import pytest

from app.services import overdue_service
from app.services.notification_service import NotificationEntity

REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")
ACTION_ID = UUID("20000000-0000-0000-0000-000000000001")
ASSIGNMENT_ID = UUID("30000000-0000-0000-0000-000000000001")
ASSIGNEE_ID = UUID("00000000-0000-0000-0000-000000000004")


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None


class FakeConnection:
    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetch(self, query: str, as_of: datetime) -> list[dict[str, object]]:
        assert "action.due_at < $1" in query
        assert as_of.tzinfo is not None
        return [
            {
                "corrective_action_id": ACTION_ID,
                "report_id": REPORT_ID,
                "rework_count": 2,
                "assignment_id": ASSIGNMENT_ID,
                "assignee_id": ASSIGNEE_ID,
            }
        ]


def test_daily_overdue_job_uses_existing_notification_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeConnection()
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_connection() -> AsyncIterator[FakeConnection]:
        yield fake

    async def fake_send(
        recipient: UUID,
        kind: str,
        entity: NotificationEntity,
        payload: dict[str, object],
        *,
        transaction_connection: FakeConnection,
        delivery_date: date | None = None,
    ) -> dict[str, object]:
        captured.update(
            recipient=recipient,
            kind=kind,
            entity=entity,
            payload=payload,
            transaction_connection=transaction_connection,
            delivery_date=delivery_date,
        )
        return captured

    monkeypatch.setattr(overdue_service, "connection", fake_connection)
    monkeypatch.setattr(overdue_service, "send_notification", fake_send)
    sent = asyncio.run(
        overdue_service.send_daily_overdue_notifications(
            as_of=datetime(2026, 8, 23, 0, 30, tzinfo=timezone.utc)
        )
    )

    assert sent == 1
    assert captured["recipient"] == ASSIGNEE_ID
    assert captured["kind"] == "overdue"
    assert captured["entity"] == NotificationEntity("corrective_action", ACTION_ID)
    assert captured["delivery_date"] == date(2026, 8, 23)
    assert captured["payload"] == {
        "report_id": REPORT_ID,
        "assignment_id": ASSIGNMENT_ID,
        "corrective_action_id": ACTION_ID,
        "rework_count": 2,
    }


def test_daily_overdue_job_rejects_naive_clock_values() -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            overdue_service.send_daily_overdue_notifications(
                as_of=datetime(2026, 8, 23, 8, 0)
            )
        )
