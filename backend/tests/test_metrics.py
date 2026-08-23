"""Verify metric authorization, units, and scheduler wiring without a database."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

import pytest

from app.config import get_settings
from app.domain.enums import ActorType, ReportStatus, Role
from app.scheduler import OVERDUE_JOB_ID, build_scheduler
from app.services import metrics_service
from app.services.metrics_service import MetricsError, get_metrics_summary
from app.services.report_service import Actor

REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")


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
    def transaction(self, **_: object) -> FakeTransaction:
        return FakeTransaction()

    async def fetch(self, *_: object) -> list[dict[str, object]]:
        return [
            {"status": ReportStatus.UNDER_REVIEW.value, "report_count": 3},
            {"status": ReportStatus.ACTION_ASSIGNED.value, "report_count": 2},
        ]

    async def fetchrow(self, *_: object) -> dict[str, object]:
        return {
            "overdue_count": 1,
            "rework_rate": 0.5,
            "median_verification_cycles_to_close": 2.0,
            "median_submitted_to_under_review_seconds": 180.0,
            "median_submitted_to_action_assigned_seconds": 3600.0,
            "median_action_assigned_to_verified_closed_seconds": 7200.0,
            "reviewer_correction_rate": 0.25,
        }


def test_metrics_summary_preserves_zero_statuses_and_explicit_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeConnection()

    @asynccontextmanager
    async def fake_connection() -> AsyncIterator[FakeConnection]:
        yield fake

    monkeypatch.setattr(metrics_service, "connection", fake_connection)
    summary = asyncio.run(
        get_metrics_summary(Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER))
    )

    assert summary.open_by_status[ReportStatus.UNDER_REVIEW.value] == 3
    assert summary.open_by_status[ReportStatus.SUBMITTED.value] == 0
    assert ReportStatus.VERIFIED_CLOSED.value not in summary.open_by_status
    assert summary.overdue_count == 1
    assert summary.rework_rate == 0.5
    assert summary.median_submitted_to_under_review_seconds == 180.0


@pytest.mark.parametrize(
    "actor",
    [
        Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        Actor.ai(),
        Actor.system(),
    ],
)
def test_metrics_are_reviewer_or_admin_only(actor: Actor) -> None:
    with pytest.raises(MetricsError) as error:
        asyncio.run(get_metrics_summary(actor))
    assert error.value.code == "metrics_actor_forbidden"


def test_scheduler_registers_one_daily_site_timezone_job() -> None:
    scheduler = build_scheduler()
    jobs = scheduler.get_jobs()

    assert [job.id for job in jobs] == [OVERDUE_JOB_ID]
    assert str(get_settings().overdue_notification_hour) in str(jobs[0].trigger)
    assert str(jobs[0].trigger.timezone) == get_settings().site_timezone
