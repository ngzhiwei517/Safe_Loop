"""Expose reviewer lesson editing and publication as machine-coded contracts."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict

from app.api.deps import current_actor
from app.config import get_settings
from app.domain.transitions import TransitionError
from app.services.briefing_service import (
    BriefingEdit,
    BriefingError,
    QuizEdit,
    get_managed_briefing,
    list_managed_briefings,
    publish_briefing,
    save_briefing,
)
from app.services.report_service import Actor

router = APIRouter(prefix="/briefings/manage", tags=["briefings"])


class QuizEditRequest(BaseModel):
    """Receive every editable field for one quiz question."""

    position: int
    question: dict[str, str]
    explanation: dict[str, str]
    options: list[dict[str, str]]
    correct_option: int

    model_config = ConfigDict(extra="forbid")


class BriefingEditRequest(BaseModel):
    """Receive one complete reviewer save without splitting locale updates."""

    body: dict[str, str]
    quiz_questions: list[QuizEditRequest]
    target_activity: str | None = None
    target_location: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    model_config = ConfigDict(extra="forbid")


def briefing_error(error: BriefingError) -> HTTPException:
    """Map briefing codes while keeping readable UI copy in the frontend."""
    code_status = {
        "briefing_actor_forbidden": status.HTTP_403_FORBIDDEN,
        "briefing_not_found": status.HTTP_404_NOT_FOUND,
        "briefing_not_draft": status.HTTP_409_CONFLICT,
        "briefing_not_editable": status.HTTP_409_CONFLICT,
        "briefing_publish_conflict": status.HTTP_409_CONFLICT,
        "briefing_token_conflict": status.HTTP_409_CONFLICT,
        "briefing_report_state_invalid": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        {"code": error.code, "message": error.message},
    )


def _transition_error(error: TransitionError) -> HTTPException:
    code_status = {
        "illegal_transition": status.HTTP_409_CONFLICT,
        "terminal_state": status.HTTP_409_CONFLICT,
        "role_not_permitted": status.HTTP_403_FORBIDDEN,
        "actor_not_permitted": status.HTTP_403_FORBIDDEN,
        "database_guard": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


def _edit(payload: BriefingEditRequest) -> BriefingEdit:
    timezone = ZoneInfo(get_settings().site_timezone)
    return BriefingEdit(
        body=payload.body,
        questions=[
            QuizEdit(
                position=question.position,
                question=question.question,
                explanation=question.explanation,
                options=question.options,
                correct_option=question.correct_option,
            )
            for question in payload.quiz_questions
        ],
        target_activity=payload.target_activity,
        target_location=payload.target_location,
        valid_from=(
            datetime.combine(payload.valid_from, time.min, timezone)
            if payload.valid_from is not None
            else None
        ),
        valid_to=(
            datetime.combine(payload.valid_to, time.max, timezone)
            if payload.valid_to is not None
            else None
        ),
    )


@router.get("")
async def get_briefings(
    actor: Actor = Depends(current_actor),
) -> list[dict[str, object]]:
    """List all draft and published versions for the reviewer workbench."""
    try:
        rows = await list_managed_briefings(actor)
    except BriefingError as error:
        raise briefing_error(error) from error
    return cast(list[dict[str, object]], jsonable_encoder(rows))


@router.get("/{briefing_id}")
async def get_briefing(
    briefing_id: UUID,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Return one briefing version with all quiz editing fields."""
    try:
        row = await get_managed_briefing(briefing_id, actor)
    except BriefingError as error:
        raise briefing_error(error) from error
    return cast(dict[str, object], jsonable_encoder(row))


@router.patch("/{briefing_id}")
async def patch_briefing(
    briefing_id: UUID,
    payload: BriefingEditRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Save a draft or fork a published version before editing it."""
    try:
        row = await save_briefing(briefing_id, actor, _edit(payload))
    except BriefingError as error:
        raise briefing_error(error) from error
    return cast(dict[str, object], jsonable_encoder(row))


@router.post("/{briefing_id}/publish")
async def post_briefing_publish(
    briefing_id: UUID,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Approve one complete draft and perform the first lesson transition."""
    try:
        row = await publish_briefing(briefing_id, actor)
    except BriefingError as error:
        raise briefing_error(error) from error
    except TransitionError as error:
        raise _transition_error(error) from error
    return cast(dict[str, object], jsonable_encoder(row))
