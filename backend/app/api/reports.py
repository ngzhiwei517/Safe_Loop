"""Expose the thin HTTP surface for report creation, reads, and transitions."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.deps import current_actor
from app.domain.enums import ReportStatus
from app.domain.transitions import TransitionError, allowed_targets
from app.services.report_service import Actor, create_report, get_report, get_timeline, transition_report

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReportRequest(BaseModel):
    """Fields needed to create a draft observation."""

    description_original: str = Field(min_length=1)
    lang_original: str = "en"
    urgency: str = "medium"
    location_text: str | None = None
    activity: str | None = None
    is_confidential: bool = False


class TransitionRequest(BaseModel):
    """Requested state-machine edge and its optional audit context."""

    target: ReportStatus
    reason: str | None = None
    metadata: dict[str, Any] | None = None


def transition_error(error: TransitionError) -> HTTPException:
    """Map machine error codes to the HTTP contract without user-facing prose."""
    code_status = {
        "illegal_transition": status.HTTP_409_CONFLICT,
        "terminal_state": status.HTTP_409_CONFLICT,
        "role_not_permitted": status.HTTP_403_FORBIDDEN,
        "actor_not_permitted": status.HTTP_403_FORBIDDEN,
        "reason_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "unknown_event": status.HTTP_400_BAD_REQUEST,
        "database_guard": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_report(payload: CreateReportRequest, actor: Actor = Depends(current_actor)) -> dict[str, UUID]:
    """Create a draft owned by the authenticated debug actor."""
    if actor.profile_id is None:
        raise HTTPException(403, {"code": "profile_required", "message": "human profile is required"})
    report_id = await create_report(
        actor.profile_id,
        payload.description_original,
        lang_original=payload.lang_original,
        urgency=payload.urgency,
        location_text=payload.location_text,
        activity=payload.activity,
        is_confidential=payload.is_confidential,
    )
    return {"id": report_id}


@router.get("/{report_id}")
async def report_detail(report_id: UUID, actor: Actor = Depends(current_actor)) -> dict[str, object]:
    """Return a report and the legal targets for the calling actor."""
    report = await get_report(report_id)
    if report is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    source = ReportStatus(report["status"])
    result = dict(report)
    result["available_transitions"] = [
        target.value for target in allowed_targets(source, actor.actor_type, actor.role)
    ]
    return cast(dict[str, object], jsonable_encoder(result))


@router.get("/{report_id}/timeline")
async def report_timeline(report_id: UUID, actor: Actor = Depends(current_actor)) -> list[dict[str, object]]:
    """Return the report's audit timeline."""
    del actor
    if await get_report(report_id) is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    return cast(
        list[dict[str, object]],
        jsonable_encoder([dict(row) for row in await get_timeline(report_id)]),
    )


@router.post("/{report_id}/transition")
async def post_transition(
    report_id: UUID,
    payload: TransitionRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Apply one legal transition through the sole status-writing service."""
    try:
        report = await transition_report(
            report_id,
            payload.target,
            actor,
            reason=payload.reason,
            metadata=payload.metadata,
        )
    except TransitionError as error:
        raise transition_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(report)))
