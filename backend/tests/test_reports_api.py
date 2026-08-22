"""Prove report reads expose only server-authorised actions and timelines."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
import pytest

from app.api import reports as reports_api
from app.api.reports import TransitionRequest
from app.domain.enums import ActorType, ReportStatus, Role
from app.domain.transitions import TRANSITIONS
from app.services.report_service import Actor

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

    monkeypatch.setattr(reports_api, "get_report", fake_report)
    monkeypatch.setattr(reports_api, "get_signed_report_media", fake_media)


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
    assert reviewer_result["available_transitions"] == [
        {"event": "reject", "target": "rejected", "requires_reason": True},
        {
            "event": "request_info",
            "target": "info_requested",
            "requires_reason": True,
        },
        {"event": "escalate", "target": "escalated", "requires_reason": True},
        {
            "event": "approve_action",
            "target": "action_assigned",
            "requires_reason": False,
        },
    ]


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
                Actor(ActorType.HUMAN, OTHER_REPORTER_ID, Role.REPORTER),
            )
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "report_forbidden"


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
