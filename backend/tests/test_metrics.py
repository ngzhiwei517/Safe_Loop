"""Verify metric authorization, units, and scheduler wiring without a database."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.api.metrics import operational_metrics
from app.config import get_settings
from app.domain.enums import ActorType, ReportStatus, Role
from app.scheduler import OVERDUE_JOB_ID, build_scheduler
from app.services import metrics_service
from app.services.metrics_service import MetricsError, get_metrics_summary
from app.services.report_service import Actor

REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
BRIEFING_ID = UUID("10000000-0000-0000-0000-000000000001")
QUESTION_ONE_ID = UUID("20000000-0000-0000-0000-000000000001")
QUESTION_TWO_ID = UUID("20000000-0000-0000-0000-000000000002")


def test_operational_metrics_are_restricted_to_operations_roles() -> None:
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            operational_metrics(
                Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER)
            )
        )
    assert error.value.status_code == 403

    reviewer_result = asyncio.run(
        operational_metrics(
            Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
        )
    )
    assert set(reviewer_result) == {"latency", "errors"}


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

    async def fetch(self, query: str, *_: object) -> list[dict[str, object]]:
        if "group by status" in query:
            return [
                {"status": ReportStatus.UNDER_REVIEW.value, "report_count": 3},
                {"status": ReportStatus.ACTION_ASSIGNED.value, "report_count": 2},
            ]
        if "ranked_responses" in query:
            return [
                {
                    "question_id": QUESTION_ONE_ID,
                    "briefing_id": BRIEFING_ID,
                    "position": 1,
                    "question": {"en": "Question one", "zh-CN": "问题一"},
                    "first_attempt_count": 4,
                    "first_attempt_correct_count": 3,
                    "first_attempt_wrong_count": 1,
                    "first_attempt_pass_rate": 0.75,
                },
                {
                    "question_id": QUESTION_TWO_ID,
                    "briefing_id": BRIEFING_ID,
                    "position": 2,
                    "question": {"en": "Question two", "zh-CN": "问题二"},
                    "first_attempt_count": 4,
                    "first_attempt_correct_count": 2,
                    "first_attempt_wrong_count": 2,
                    "first_attempt_pass_rate": 0.5,
                },
            ]
        if "closed_reports" in query:
            closed_at = datetime(2026, 8, 20, tzinfo=timezone.utc)
            return [
                {
                    "category": "work_at_height",
                    "location": "Block A",
                    "report_count": 3,
                    "recurrence_count": 2,
                    "first_closed_at": closed_at,
                    "latest_closed_at": closed_at,
                    "responsible_rework": [
                        {
                            "profile_id": str(REPORTER_ID),
                            "display_name": "Responsible team",
                            "action_count": 4,
                            "reworked_action_count": 1,
                            "rework_rate": 0.25,
                        }
                    ],
                }
            ]
        if "report.description_original as confirmed_text" in query:
            return [
                {
                    "id": UUID("30000000-0000-0000-0000-000000000001"),
                    "input_mode": "typed",
                    "confirmed_text": "Typed report",
                    "text_raw": None,
                    "detected_locale": None,
                },
                {
                    "id": UUID("30000000-0000-0000-0000-000000000002"),
                    "input_mode": "voice",
                    "confirmed_text": "六楼没有护栏",
                    "text_raw": "六楼没有护栏",
                    "detected_locale": "zh-CN",
                },
                {
                    "id": UUID("30000000-0000-0000-0000-000000000003"),
                    "input_mode": "voice_edited",
                    "confirmed_text": "Guardrail fixed",
                    "text_raw": "Guardrail fixd",
                    "detected_locale": "en-SG",
                },
            ]
        if "from transcription_attempts" in query:
            return [
                {"locale": "en-SG", "attempt_count": 1, "failure_count": 0},
                {"locale": "zh-CN", "attempt_count": 2, "failure_count": 1},
            ]
        raise AssertionError("unexpected metrics query")

    async def fetchrow(self, query: str, *_: object) -> dict[str, object]:
        if "eligible_responses" in query:
            return {
                "published_briefing_count": 2,
                "crew_reach": 4,
                "anonymous_quiz_response_count": 3,
                "first_attempt_count": 8,
                "first_attempt_pass_rate": 0.625,
            }
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
    assert summary.published_briefing_count == 2
    assert summary.crew_reach == 4
    assert summary.anonymous_quiz_response_count == 3
    assert summary.first_attempt_count == 8
    assert summary.first_attempt_pass_rate == 0.625
    assert summary.question_performance[0].question["zh-CN"] == "问题一"
    assert summary.questions_most_often_wrong[0].question_id == QUESTION_TWO_ID
    assert summary.repeat_hazards[0].recurrence_count == 2
    assert summary.repeat_hazards[0].responsible_rework[0].rework_rate == 0.25
    assert summary.report_count == 3
    assert summary.voice_report_share == pytest.approx(2 / 3)
    assert summary.transcript_accepted_unedited_rate == 0.5
    assert summary.median_voice_edit_distance == 0.5
    assert summary.transcription_failure_rate == pytest.approx(1 / 3)
    assert summary.voice_by_detected_locale[1].detected_locale == "zh-CN"
    assert summary.voice_by_detected_locale[1].transcription_failure_rate == 0.5


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
