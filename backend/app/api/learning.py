"""Expose public crew briefings and signed-in learning discovery."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict

from app.api.deps import current_actor, optional_actor
from app.services.learning_service import (
    LearningError,
    get_public_briefing,
    list_learning_briefings,
    submit_quiz_answer,
)
from app.services.report_service import Actor

router = APIRouter(prefix="/briefings", tags=["learning"])


class QuizAnswerRequest(BaseModel):
    """Receive one answer without trusting the browser to grade it."""

    question_id: UUID
    selected_option: int

    model_config = ConfigDict(extra="forbid")


def learning_error(error: LearningError) -> HTTPException:
    """Map learning codes while keeping readable copy in the frontend."""
    code_status = {
        "learning_actor_forbidden": status.HTTP_403_FORBIDDEN,
        "briefing_inactive": status.HTTP_404_NOT_FOUND,
        "quiz_question_not_found": status.HTTP_404_NOT_FOUND,
        "quiz_option_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "quiz_rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        {"code": error.code, "message": error.message},
        headers={"Retry-After": "60"} if error.code == "quiz_rate_limited" else None,
    )


@router.get("")
async def get_learning_feed(
    actor: Actor = Depends(current_actor),
) -> list[dict[str, object]]:
    """List active published lessons in worker-relevant order."""
    try:
        rows = await list_learning_briefings(actor)
    except LearningError as error:
        raise learning_error(error) from error
    return cast(list[dict[str, object]], jsonable_encoder(rows))


@router.get("/{token}")
async def get_briefing_by_token(token: str) -> dict[str, object]:
    """Return one active public briefing without answer keys."""
    try:
        row = await get_public_briefing(token)
    except LearningError as error:
        raise learning_error(error) from error
    return cast(dict[str, object], jsonable_encoder(row))


@router.post("/{token}/quiz")
async def post_quiz_answer(
    token: str,
    payload: QuizAnswerRequest,
    request: Request,
    actor: Actor | None = Depends(optional_actor),
) -> dict[str, object]:
    """Record a bounded anonymous or signed-in answer and return immediate grading."""
    client_ip = request.client.host if request.client is not None else "unknown"
    try:
        result = await submit_quiz_answer(
            token,
            payload.question_id,
            payload.selected_option,
            actor=actor,
            client_ip=client_ip,
        )
    except LearningError as error:
        raise learning_error(error) from error
    return cast(dict[str, object], jsonable_encoder(result))
