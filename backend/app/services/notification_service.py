"""Keep every in-app notification write behind one transaction-aware seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Literal
from uuid import UUID

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from app.db import connection
from app.domain.enums import ActorType
from app.services.report_service import Actor

NotificationKind = Literal[
    "assigned",
    "sent_back",
    "overdue",
    "info_requested",
    "alert_raised",
    "briefing_published",
    "report_closed",
]

NOTIFICATION_KINDS = frozenset(
    {
        "assigned",
        "sent_back",
        "overdue",
        "info_requested",
        "alert_raised",
        "briefing_published",
        "report_closed",
    }
)


class NotificationError(Exception):
    """Carry a stable notification code for the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NotificationEntity:
    """Identify the locale-independent object a notification opens."""

    entity_type: str
    entity_id: UUID


def _normalise_payload(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if type(value) in {int, float}:
        return value
    if value is None:
        return None
    if isinstance(value, list):
        return [_normalise_payload(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {str(key): _normalise_payload(item) for key, item in value.items()}
    raise NotificationError(
        "notification_payload_invalid",
        "notification payload values must be identifiers or numbers",
    )


async def send_notification(
    recipient: UUID,
    kind: NotificationKind,
    entity: NotificationEntity,
    payload: dict[str, object],
    *,
    transaction_connection: PoolConnectionProxy[asyncpg.Record],
    delivery_date: date | None = None,
) -> asyncpg.Record:
    """Insert through the causing event's connection so both changes commit together."""
    if kind not in NOTIFICATION_KINDS:
        raise NotificationError("notification_kind_invalid", "notification kind is invalid")
    if (kind == "overdue") is not (delivery_date is not None):
        raise NotificationError(
            "notification_delivery_date_invalid",
            "only overdue notifications require a delivery date",
        )
    normalised = _normalise_payload(payload)
    row = await transaction_connection.fetchrow(
        """
        insert into notifications (
          recipient_id, kind, entity_type, entity_id, payload, delivery_date
        )
        values ($1, $2, $3, $4, $5::jsonb, $6)
        on conflict (
          recipient_id, kind, entity_type, entity_id, delivery_date
        ) where kind = 'overdue'
        do nothing
        returning *
        """,
        recipient,
        kind,
        entity.entity_type,
        entity.entity_id,
        json.dumps(normalised),
        delivery_date,
    )
    if row is None and kind == "overdue":
        row = await transaction_connection.fetchrow(
            """
            select *
            from notifications
            where recipient_id = $1
              and kind = 'overdue'
              and entity_type = $2
              and entity_id = $3
              and delivery_date = $4
            """,
            recipient,
            entity.entity_type,
            entity.entity_id,
            delivery_date,
        )
    if row is None:
        raise RuntimeError("database did not return notification")
    return row


async def list_notifications(
    actor: Actor,
    *,
    limit: int = 50,
) -> tuple[list[asyncpg.Record], int, int, int]:
    """Return the actor's inbox without changing read state."""
    if actor.actor_type is not ActorType.HUMAN or actor.profile_id is None:
        raise NotificationError("notification_actor_forbidden", "human profile is required")
    if not 1 <= limit <= 100:
        raise NotificationError("notification_limit_invalid", "notification limit is invalid")
    async with connection() as conn:
        rows = await conn.fetch(
            """
            select *
            from notifications
            where recipient_id = $1
            order by (read_at is null) desc, created_at desc, id desc
            limit $2
            """,
            actor.profile_id,
            limit,
        )
        counts = await conn.fetchrow(
            """
            select
              count(*) filter (where read_at is null)::integer as unread_count,
              count(*) filter (
                where read_at is null and kind = 'sent_back'
              )::integer as priority_unread_count,
              (
                select count(*)::integer
                from corrective_actions action
                join report_assignments assignment
                  on assignment.id = action.assignment_id
                 and assignment.report_id = action.report_id
                 and assignment.active
                join reports report on report.id = action.report_id
                where assignment.assignee_id = $1
                  and action.status = 'assigned'::action_status
                  and action.rework_count >= 1
                  and report.status = 'action_assigned'::report_status
              ) as unresolved_sent_back_count
            from notifications
            where recipient_id = $1
            """,
            actor.profile_id,
        )
    if counts is None:
        raise RuntimeError("database did not return notification counts")
    return (
        rows,
        counts["unread_count"],
        counts["priority_unread_count"],
        counts["unresolved_sent_back_count"],
    )


async def mark_notification_read(notification_id: UUID, actor: Actor) -> asyncpg.Record:
    """Mark only the recipient's item read, and only after an explicit API call."""
    if actor.actor_type is not ActorType.HUMAN or actor.profile_id is None:
        raise NotificationError("notification_actor_forbidden", "human profile is required")
    async with connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "select * from notifications where id = $1 for update",
                notification_id,
            )
            if existing is None:
                raise NotificationError("notification_not_found", "notification does not exist")
            if existing["recipient_id"] != actor.profile_id:
                raise NotificationError("notification_forbidden", "notification belongs to another profile")
            if existing["read_at"] is not None:
                return existing
            updated = await conn.fetchrow(
                "update notifications set read_at = now() where id = $1 returning *",
                notification_id,
            )
            if updated is None:
                raise RuntimeError("notification disappeared while marking read")
            return updated
