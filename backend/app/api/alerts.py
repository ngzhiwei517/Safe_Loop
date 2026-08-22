"""Expose urgent-alert actions while leaving all mutations in the service layer."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.deps import current_actor
from app.services.alert_service import (
    AlertError,
    acknowledge_alert,
    get_alert,
    list_alerts,
    raise_alert,
    resolve_alert,
)
from app.services.report_service import Actor

router = APIRouter(prefix="/alerts", tags=["alerts"])


class RaiseAlertRequest(BaseModel):
    """Identify the draft and whatever location the reporter has entered."""

    report_id: UUID
    location_text: str | None = Field(default=None, max_length=500)


class ResolveAlertRequest(BaseModel):
    """Require the responder's explicit resolution evidence."""

    resolution_note: str = Field(min_length=1, max_length=2000)


def alert_error(error: AlertError) -> HTTPException:
    """Map alert errors to stable machine-readable API responses."""
    code_status = {
        "alert_actor_forbidden": status.HTTP_403_FORBIDDEN,
        "alert_report_forbidden": status.HTTP_403_FORBIDDEN,
        "alert_forbidden": status.HTTP_403_FORBIDDEN,
        "alert_not_found": status.HTTP_404_NOT_FOUND,
        "alert_report_not_found": status.HTTP_404_NOT_FOUND,
        "alert_requires_draft": status.HTTP_409_CONFLICT,
        "alert_no_recipients": status.HTTP_503_SERVICE_UNAVAILABLE,
        "alert_no_escalation_recipients": status.HTTP_503_SERVICE_UNAVAILABLE,
        "alert_resolution_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "alert_limit_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "alert_threshold_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_alert(
    payload: RaiseAlertRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Raise immediately on a draft; retries return the existing alert."""
    try:
        row = await raise_alert(
            payload.report_id,
            actor,
            location_text=payload.location_text,
        )
    except AlertError as error:
        raise alert_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(row)))


@router.get("")
async def alert_list(
    limit: int = Query(default=100, ge=1, le=200),
    actor: Actor = Depends(current_actor),
) -> list[dict[str, object]]:
    """Return reviewer/admin alerts with unresolved and unseen items first."""
    try:
        rows = await list_alerts(actor, limit=limit)
    except AlertError as error:
        raise alert_error(error) from error
    return cast(list[dict[str, object]], jsonable_encoder([dict(row) for row in rows]))


@router.get("/{alert_id}")
async def alert_detail(
    alert_id: UUID,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Let the reporter poll the acknowledgement fields that drive truthful copy."""
    try:
        row = await get_alert(alert_id, actor)
    except AlertError as error:
        raise alert_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(row)))


@router.post("/{alert_id}/acknowledge")
async def post_acknowledge_alert(
    alert_id: UUID,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Record the named human and timestamp as a deliberate act."""
    try:
        row = await acknowledge_alert(alert_id, actor)
    except AlertError as error:
        raise alert_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(row)))


@router.post("/{alert_id}/resolve")
async def post_resolve_alert(
    alert_id: UUID,
    payload: ResolveAlertRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Close an alert only with a non-empty resolution note."""
    try:
        row = await resolve_alert(
            alert_id,
            actor,
            resolution_note=payload.resolution_note,
        )
    except AlertError as error:
        raise alert_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(row)))
