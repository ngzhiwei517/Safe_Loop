"""Exercise verification validation and the HTTP contract without a database."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
import pytest

from app.api import reports as reports_api
from app.api.reports import VerifyRequest, verification_error
from app.domain.enums import ActorType, Role
from app.services.report_service import Actor
from app.services.verification_service import (
    VerificationError,
    VerificationResult,
    verify_report,
)

REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
ACTION_ID = UUID("50000000-0000-0000-0000-000000000001")
ASSIGNMENT_ID = UUID("40000000-0000-0000-0000-000000000001")
VERIFICATION_ID = UUID("60000000-0000-0000-0000-000000000001")


@pytest.mark.parametrize("actor", [Actor.ai(), Actor.system()])
def test_machine_actor_is_refused_before_database_access(actor: Actor) -> None:
    with pytest.raises(VerificationError) as error:
        asyncio.run(
            verify_report(
                REPORT_ID,
                actor,
                passed=True,
                checklist=None,
                notes="Evidence inspected.",
            )
        )
    assert error.value.code == "verification_actor_forbidden"


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_failed_verification_refuses_blank_reason(reason: str | None) -> None:
    with pytest.raises(VerificationError) as error:
        asyncio.run(
            verify_report(
                REPORT_ID,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                passed=False,
                checklist=None,
                notes="Evidence inspected.",
                reason=reason,
                new_due_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            )
        )
    assert error.value.code == "verification_reason_required"


@pytest.mark.parametrize("reason", ["not done", "Not done.", "未完成。"])
def test_failed_verification_refuses_a_generic_reason(reason: str) -> None:
    with pytest.raises(VerificationError) as error:
        asyncio.run(
            verify_report(
                REPORT_ID,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                passed=False,
                checklist=None,
                notes="Evidence inspected.",
                reason=reason,
                new_due_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            )
        )
    assert error.value.code == "verification_reason_too_vague"


def test_failed_verification_requires_a_new_due_date() -> None:
    with pytest.raises(VerificationError) as error:
        asyncio.run(
            verify_report(
                REPORT_ID,
                Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
                passed=False,
                checklist=None,
                notes="Evidence inspected.",
                reason="The lower anchor still moves when pulled.",
            )
        )
    assert error.value.code == "verification_due_at_required"


def test_verification_endpoint_passes_the_complete_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    due_at = datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc)

    async def fake_verify(
        report_id: UUID,
        actor: Actor,
        **values: object,
    ) -> VerificationResult:
        captured.update({"report_id": report_id, "actor": actor, **values})
        return VerificationResult(
            verification={"id": VERIFICATION_ID},  # type: ignore[arg-type]
            report={"id": report_id, "status": "action_assigned", "closed_at": None},  # type: ignore[arg-type]
            action={"id": ACTION_ID, "status": "assigned", "rework_count": 1},  # type: ignore[arg-type]
            assignment={"id": ASSIGNMENT_ID, "due_at": due_at},  # type: ignore[arg-type]
        )

    monkeypatch.setattr(reports_api, "verify_report", fake_verify)
    actor = Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER)
    payload = VerifyRequest(
        passed=False,
        checklist={"hazard_removed": False},
        notes="The lower anchor was pull-tested.",
        reason="The lower anchor still moves when pulled.",
        new_due_at=due_at,
    )

    result = asyncio.run(reports_api.post_verification(REPORT_ID, payload, actor))

    assert result["verification_id"] == str(VERIFICATION_ID)
    assert result["status"] == "action_assigned"
    assert result["rework_count"] == 1
    assert captured == {
        "report_id": REPORT_ID,
        "actor": actor,
        "passed": False,
        "checklist": {"hazard_removed": False},
        "notes": "The lower anchor was pull-tested.",
        "reason": "The lower anchor still moves when pulled.",
        "new_due_at": due_at,
    }


def test_verification_validation_maps_to_a_clean_422() -> None:
    error = verification_error(
        VerificationError(
            "verification_reason_required",
            "failed verification requires a specific deficiency",
        )
    )
    assert isinstance(error, HTTPException)
    assert error.status_code == 422
    assert error.detail == {
        "code": "verification_reason_required",
        "message": "failed verification requires a specific deficiency",
    }
