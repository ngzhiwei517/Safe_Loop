"""Prove corrective-action submission contracts before database integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
import pytest

from app.api import reports as reports_api
from app.api.reports import ActionSubmitRequest
from app.domain.enums import ActorType, Role
from app.services.action_service import (
    ActionError,
    ActionSubmissionResult,
    submit_action,
)
from app.services.report_service import Actor

REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")
ACTION_ID = UUID("50000000-0000-0000-0000-000000000001")
MEDIA_ID = UUID("60000000-0000-0000-0000-000000000001")
TRANSCRIPT_ID = UUID("70000000-0000-0000-0000-000000000001")
RESPONSIBLE_ID = UUID("00000000-0000-0000-0000-000000000004")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")


def responsible_actor() -> Actor:
    return Actor(ActorType.HUMAN, RESPONSIBLE_ID, Role.RESPONSIBLE)


def test_done_without_note_or_photo_is_a_specific_422() -> None:
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            reports_api.post_action_submission(
                REPORT_ID,
                ACTION_ID,
                ActionSubmitRequest(completed_note="   "),
                responsible_actor(),
            )
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "action_evidence_required"


def test_only_a_responsible_human_can_submit_action_evidence() -> None:
    with pytest.raises(ActionError) as error:
        asyncio.run(
            submit_action(
                REPORT_ID,
                ACTION_ID,
                Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
                completed_note="Guardrail secured.",
                media_ids=[],
            )
        )

    assert error.value.code == "action_actor_forbidden"


def test_action_endpoint_passes_registered_media_ids_to_atomic_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_submit(
        report_id: UUID,
        action_id: UUID,
        actor: Actor,
        **values: object,
    ) -> ActionSubmissionResult:
        captured.update(
            {"report_id": report_id, "action_id": action_id, "actor": actor, **values}
        )
        return ActionSubmissionResult(
            action={
                "id": action_id,
                "completed_note": "Guardrail secured.",
                "submitted_at": datetime(2026, 8, 23, tzinfo=timezone.utc),
            },  # type: ignore[arg-type]
            report={"id": report_id, "status": "action_submitted"},  # type: ignore[arg-type]
            media_ids=(MEDIA_ID,),
        )

    monkeypatch.setattr(reports_api, "submit_action", fake_submit)
    actor = responsible_actor()
    result = asyncio.run(
        reports_api.post_action_submission(
            REPORT_ID,
            ACTION_ID,
            ActionSubmitRequest(
                completed_note="Guardrail secured.",
                media_ids=[MEDIA_ID],
                transcript_id=TRANSCRIPT_ID,
            ),
            actor,
        )
    )

    assert result["status"] == "action_submitted"
    assert result["media_ids"] == [str(MEDIA_ID)]
    assert captured == {
        "report_id": REPORT_ID,
        "action_id": ACTION_ID,
        "actor": actor,
        "completed_note": "Guardrail secured.",
        "media_ids": [MEDIA_ID],
        "transcript_id": TRANSCRIPT_ID,
    }
