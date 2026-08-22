"""Expose the thin HTTP surface for report creation, reads, and transitions."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.deps import current_actor
from app.domain.enums import InputMode, MediaPhase, ReportStatus
from app.domain.transitions import TransitionError, allowed_targets, find
from app.services.media_service import (
    MediaError,
    assert_report_readable,
    get_signed_report_media,
    register_report_media,
)
from app.services.report_service import Actor, create_report, get_report, get_timeline, transition_report

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReportRequest(BaseModel):
    """Fields needed to create a draft observation."""

    description_original: str = Field(min_length=1)
    lang_original: str = "en"
    urgency: str = "medium"
    location_text: str | None = None
    activity: str | None = None
    level_or_zone: str | None = None
    grid_ref: str | None = None
    is_confidential: bool = False
    input_mode: InputMode = InputMode.TYPED


class TransitionRequest(BaseModel):
    """Requested state-machine edge and its optional audit context."""

    target: ReportStatus
    reason: str | None = None
    metadata: dict[str, Any] | None = None


class RegisterMediaRequest(BaseModel):
    """Describe an object already uploaded to private Supabase Storage."""

    storage_path: str = Field(min_length=1, max_length=1024)
    mime_type: str = Field(min_length=1, max_length=100)
    phase: MediaPhase
    caption: str | None = Field(default=None, max_length=500)


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


def media_error(error: MediaError) -> HTTPException:
    """Map media failures to stable machine-readable HTTP contracts."""
    code_status = {
        "report_not_found": status.HTTP_404_NOT_FOUND,
        "report_forbidden": status.HTTP_403_FORBIDDEN,
        "media_actor_not_permitted": status.HTTP_403_FORBIDDEN,
        "media_phase_not_permitted": status.HTTP_403_FORBIDDEN,
        "media_path_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_type_not_allowed": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "media_type_mismatch": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        "media_object_not_found": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_object_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_already_registered": status.HTTP_409_CONFLICT,
        "storage_not_configured": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "storage_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "storage_sign_failed": status.HTTP_502_BAD_GATEWAY,
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
        level_or_zone=payload.level_or_zone,
        grid_ref=payload.grid_ref,
        is_confidential=payload.is_confidential,
        input_mode=payload.input_mode,
    )
    return {"id": report_id}


@router.get("/{report_id}")
async def report_detail(report_id: UUID, actor: Actor = Depends(current_actor)) -> dict[str, object]:
    """Return a report and the legal targets for the calling actor."""
    report = await get_report(report_id)
    if report is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    try:
        assert_report_readable(report, actor)
        media = await get_signed_report_media(report_id)
    except MediaError as error:
        raise media_error(error) from error
    source = ReportStatus(report["status"])
    result = dict(report)
    result["media"] = media
    available = []
    for target in allowed_targets(source, actor.actor_type, actor.role):
        transition = find(source, target)
        if transition is None:
            raise RuntimeError("allowed state-machine target has no transition")
        available.append(
            {
                "event": transition.event,
                "target": transition.target.value,
                "requires_reason": transition.requires_reason,
            }
        )
    result["available_transitions"] = available
    return cast(dict[str, object], jsonable_encoder(result))


@router.post("/{report_id}/media", status_code=status.HTTP_201_CREATED)
async def post_report_media(
    report_id: UUID,
    payload: RegisterMediaRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Register one private object only after checking its stored metadata."""
    try:
        media = await register_report_media(
            report_id,
            actor,
            storage_path=payload.storage_path,
            mime_type=payload.mime_type,
            phase=payload.phase,
            caption=payload.caption,
        )
    except MediaError as error:
        raise media_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(media)))


@router.get("/{report_id}/timeline")
async def report_timeline(report_id: UUID, actor: Actor = Depends(current_actor)) -> list[dict[str, object]]:
    """Return the report's audit timeline."""
    report = await get_report(report_id)
    if report is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    try:
        assert_report_readable(report, actor)
    except MediaError as error:
        raise media_error(error) from error
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
    existing_report = await get_report(report_id)
    if existing_report is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    try:
        assert_report_readable(existing_report, actor)
        report = await transition_report(
            report_id,
            payload.target,
            actor,
            reason=payload.reason,
            metadata=payload.metadata,
        )
    except MediaError as error:
        raise media_error(error) from error
    except TransitionError as error:
        raise transition_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(report)))
