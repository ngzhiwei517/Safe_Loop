"""Expose the explicit-read inbox without embedding user-facing prose."""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder

from app.api.deps import current_actor
from app.services.notification_service import (
    NotificationError,
    list_notifications,
    mark_notification_read,
)
from app.services.report_service import Actor

router = APIRouter(prefix="/notifications", tags=["notifications"])


def notification_json(row: asyncpg.Record) -> dict[str, object]:
    """Return asyncpg JSONB as JSON data instead of its wire-format string."""
    item = dict(row)
    payload = item.get("payload")
    if isinstance(payload, str):
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise RuntimeError("notification payload is not an object")
        item["payload"] = decoded
    return item


def notification_error(error: NotificationError) -> HTTPException:
    """Map notification codes to the stable developer-facing API shape."""
    code_status = {
        "notification_actor_forbidden": status.HTTP_403_FORBIDDEN,
        "notification_forbidden": status.HTTP_403_FORBIDDEN,
        "notification_not_found": status.HTTP_404_NOT_FOUND,
        "notification_limit_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "notification_payload_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "notification_kind_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


@router.get("")
async def notification_list(
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Return unread-first inbox rows without marking anything read."""
    try:
        rows, unread_count, priority_unread_count = await list_notifications(
            actor,
            limit=limit,
        )
    except NotificationError as error:
        raise notification_error(error) from error
    return cast(
        dict[str, object],
        jsonable_encoder(
            {
                "items": [notification_json(row) for row in rows],
                "unread_count": unread_count,
                "priority_unread_count": priority_unread_count,
            }
        ),
    )


@router.post("/{notification_id}/read")
async def notification_read(
    notification_id: UUID,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Mark one item read only through this deliberate endpoint."""
    try:
        row = await mark_notification_read(notification_id, actor)
    except NotificationError as error:
        raise notification_error(error) from error
    return cast(dict[str, object], jsonable_encoder(notification_json(row)))
