"""Prove report reads expose only server-authorised actions and timelines."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException
import pytest

from app.api import reports as reports_api
from app.api.reports import ReviewRequest, TransitionRequest
from app.domain.enums import ActorType, ReportStatus, ReviewDecision, Role
from app.domain.transitions import TRANSITIONS
from app.services.report_service import Actor
from app.services.review_service import ReviewResult

REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_REPORTER_ID = UUID("00000000-0000-0000-0000-000000000002")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")


def configure_report_read(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: str = "under_review",
) -> None:
    async def fake_report(_: UUID) -> dict[str, object]:
        return {
            "id": REPORT_ID,
            "reporter_id": REPORTER_ID,
            "status": status,
        }

    async def fake_media(_: UUID) -> list[dict[str, object]]:
        return []

    async def fake_clarifications(_: UUID) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(reports_api, "get_report", fake_report)
    monkeypatch.setattr(reports_api, "get_signed_report_media", fake_media)
    monkeypatch.setattr(
        reports_api,
        "list_report_clarifications",
        fake_clarifications,
    )


def test_available_transitions_differ_without_client_role_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_report_read(monkeypatch)

    reporter_result = asyncio.run(
        reports_api.report_detail(
            REPORT_ID,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
    )
    reviewer_result = asyncio.run(
        reports_api.report_detail(
            REPORT_ID,
            Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
        )
    )

    assert reporter_result["available_transitions"] == []
    assert reporter_result["latest_draft"] is None
    assert reviewer_result["latest_draft"] is None
    assert reviewer_result["available_transitions"] == [
        {
            "event": "reject",
            "target": "rejected",
            "requires_reason": True,
            "review_decision": "reject",
        },
        {
            "event": "request_info",
            "target": "info_requested",
            "requires_reason": True,
            "review_decision": "request_info",
        },
        {
            "event": "escalate",
            "target": "escalated",
            "requires_reason": True,
            "review_decision": "escalate",
        },
        {
            "event": "approve_action",
            "target": "action_assigned",
            "requires_reason": False,
            "review_decision": "approve",
        },
    ]


def test_report_detail_decodes_latest_draft_and_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_report(_: UUID) -> dict[str, object]:
        return {
            "id": REPORT_ID,
            "reporter_id": REPORTER_ID,
            "status": "under_review",
            "latest_draft": json.dumps(
                {
                    "version": 2,
                    "observed_facts": ["The Level 6 edge has no guardrail."],
                    "assumptions": ["The formwork crew owns the area."],
                    "missing_information": ["Work schedule below"],
                    "proposed_category": "work_at_height",
                    "proposed_urgency": "high",
                    "suggested_action": None,
                    "validation": "invalid",
                    "validation_errors": ["confidence_below_threshold"],
                }
            ),
        }

    async def empty_rows(_: UUID) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(reports_api, "get_report", fake_report)
    monkeypatch.setattr(reports_api, "get_signed_report_media", empty_rows)
    monkeypatch.setattr(reports_api, "list_report_clarifications", empty_rows)

    result = asyncio.run(
        reports_api.report_detail(
            REPORT_ID,
            Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
        )
    )

    draft = result["latest_draft"]
    assert isinstance(draft, dict)
    assert draft["version"] == 2
    assert draft["validation_errors"] == ["confidence_below_threshold"]


def test_review_endpoint_passes_the_atomic_payload_to_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_review(report_id: UUID, actor: Actor, **values: object) -> ReviewResult:
        captured.update({"report_id": report_id, "actor": actor, **values})
        return ReviewResult(
            review={"id": UUID("20000000-0000-0000-0000-000000000001")},  # type: ignore[arg-type]
            report={"id": report_id, "status": "info_requested"},  # type: ignore[arg-type]
            assignment_id=None,
            corrective_action_id=None,
        )

    monkeypatch.setattr(reports_api, "review_report", fake_review)
    actor = Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
    payload = ReviewRequest(
        decision=ReviewDecision.REQUEST_INFO,
        target=ReportStatus.INFO_REQUESTED,
        reason="Confirm the exclusion zone.",
        corrected_category="edge protection",
        correction_reason="Category was too broad.",
    )

    result = asyncio.run(reports_api.post_review(REPORT_ID, payload, actor))

    assert result == {
        "review_id": "20000000-0000-0000-0000-000000000001",
        "report_id": str(REPORT_ID),
        "status": "info_requested",
        "assignment_id": None,
        "corrective_action_id": None,
    }
    assert captured["report_id"] == REPORT_ID
    assert captured["actor"] == actor
    assert captured["decision"] is ReviewDecision.REQUEST_INFO
    assert captured["target"] is ReportStatus.INFO_REQUESTED
    assert captured["reason"] == "Confirm the exclusion zone."
    assert captured["corrected_category"] == "edge protection"
    assert captured["correction_reason"] == "Category was too broad."


def test_timeline_read_uses_the_same_report_authorisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_report_read(monkeypatch, status="submitted")

    async def fake_timeline(_: UUID) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(reports_api, "get_timeline", fake_timeline)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            reports_api.report_timeline(
                REPORT_ID,
                Actor(ActorType.HUMAN, OTHER_REPORTER_ID, Role.REPORTER),
            )
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "report_forbidden"


def test_transition_endpoint_refuses_a_different_reporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_report_read(monkeypatch, status="draft")

    async def must_not_transition(*_: object, **__: object) -> None:
        raise AssertionError("unauthorised transition reached the status writer")

    monkeypatch.setattr(reports_api, "transition_report", must_not_transition)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            reports_api.post_transition(
                REPORT_ID,
                TransitionRequest(target=ReportStatus.SUBMITTED),
                BackgroundTasks(),
                Actor(ActorType.HUMAN, OTHER_REPORTER_ID, Role.REPORTER),
            )
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "report_forbidden"


def test_successful_submission_schedules_intake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_report_read(monkeypatch, status="draft")

    async def fake_transition(*_: object, **__: object) -> dict[str, object]:
        return {"id": REPORT_ID, "status": "submitted"}

    monkeypatch.setattr(reports_api, "transition_report", fake_transition)
    background_tasks = BackgroundTasks()

    asyncio.run(
        reports_api.post_transition(
            REPORT_ID,
            TransitionRequest(target=ReportStatus.SUBMITTED),
            background_tasks,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
    )

    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is reports_api.run_intake
    assert background_tasks.tasks[0].args == (REPORT_ID,)


def test_answer_endpoint_schedules_intake_after_round_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clarification_id = UUID("30000000-0000-0000-0000-000000000001")

    class StoredAnswer:
        clarification = {
            "id": clarification_id,
            "report_id": REPORT_ID,
            "answered_at": None,
        }
        rerun = True

    async def fake_answer(*_: object, **__: object) -> StoredAnswer:
        return StoredAnswer()

    monkeypatch.setattr(reports_api, "answer_clarification", fake_answer)
    background_tasks = BackgroundTasks()

    result = asyncio.run(
        reports_api.post_clarification_answer(
            REPORT_ID,
            clarification_id,
            reports_api.ClarificationAnswerRequest(answer="Level 6 east edge"),
            background_tasks,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
    )

    assert result["id"] == str(clarification_id)
    assert result["round_complete"] is True
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is reports_api.run_intake
    assert background_tasks.tasks[0].args == (REPORT_ID,)


def test_every_state_machine_event_has_action_and_timeline_catalogue_keys() -> None:
    repository = Path(__file__).resolve().parents[2]
    for locale in ("en", "zh-CN"):
        messages = json.loads(
            (repository / "frontend" / "messages" / f"{locale}.json").read_text(
                encoding="utf-8"
            )
        )
        assert "timeline.event.create_report" in messages
        for status in ReportStatus:
            assert f"report.detail.waiting.{status.value}" in messages
        for actor_type in ActorType:
            assert f"timeline.actor.{actor_type.value}" in messages
        for role in Role:
            assert f"timeline.actor.{role.value}" in messages
        for transition in TRANSITIONS:
            assert f"action.{transition.event}" in messages
            assert f"timeline.event.{transition.event}" in messages
