"""Make urgent alerts immediate, attributable, idempotent, and truthful to reporters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from app.db import connection
from app.domain.enums import ActorType, ReportStatus, Role
from app.services.notification_service import NotificationEntity, send_notification
from app.services.report_service import Actor


class AlertError(Exception):
    """Carry a stable urgent-alert code to the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _require_reporter(actor: Actor) -> UUID:
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.profile_id is None
        or actor.role is not Role.REPORTER
    ):
        raise AlertError("alert_actor_forbidden", "only a reporter can raise an alert")
    return actor.profile_id


def _require_responder(actor: Actor) -> UUID:
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.profile_id is None
        or actor.role not in {Role.REVIEWER, Role.ADMIN}
    ):
        raise AlertError("alert_actor_forbidden", "reviewer or admin profile is required")
    return actor.profile_id


async def _alert_row(
    conn: PoolConnectionProxy[asyncpg.Record],
    alert_id: UUID,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        select
          alerts.*,
          reports.human_ref,
          reports.description_original,
          profiles.display_name as acknowledged_by_name
        from alerts
        join reports on reports.id = alerts.report_id
        left join profiles on profiles.id = alerts.acknowledged_by
        where alerts.id = $1
        """,
        alert_id,
    )


async def raise_alert(
    report_id: UUID,
    actor: Actor,
    *,
    location_text: str | None = None,
) -> asyncpg.Record:
    """Raise and notify on a draft without depending on submission or AI."""
    reporter_id = _require_reporter(actor)
    clean_location = location_text.strip() if location_text else None
    async with connection() as conn:
        async with conn.transaction():
            report = await conn.fetchrow(
                "select * from reports where id = $1 for update",
                report_id,
            )
            if report is None:
                raise AlertError("alert_report_not_found", "report does not exist")
            if report["reporter_id"] != reporter_id:
                raise AlertError("alert_report_forbidden", "draft belongs to another reporter")
            if ReportStatus(report["status"]) is not ReportStatus.DRAFT:
                raise AlertError("alert_requires_draft", "alert must be raised on a draft")

            existing_id = await conn.fetchval(
                "select id from alerts where report_id = $1",
                report_id,
            )
            if isinstance(existing_id, UUID):
                existing = await _alert_row(conn, existing_id)
                if existing is None:
                    raise RuntimeError("existing alert disappeared")
                return existing

            reviewers = await conn.fetch(
                "select id from profiles where role = 'reviewer' and is_on_duty order by id"
            )
            if not reviewers:
                raise AlertError("alert_no_recipients", "no on-duty reviewer can receive the alert")

            await conn.execute(
                """
                update reports
                set urgency = 'critical',
                    location_text = coalesce($2, location_text)
                where id = $1
                """,
                report_id,
                clean_location,
            )
            alert = await conn.fetchrow(
                """
                insert into alerts (report_id, raised_by, location_text)
                values ($1, $2, coalesce($3, $4))
                returning *
                """,
                report_id,
                reporter_id,
                clean_location,
                report["location_text"],
            )
            if alert is None:
                raise RuntimeError("database did not return alert")
            alert_id = alert["id"]
            await conn.execute(
                """
                insert into audit_log (
                  report_id, actor_type, actor_id, event, metadata
                )
                values ($1, 'human', $2, 'raise_alert', $3::jsonb)
                """,
                report_id,
                reporter_id,
                json.dumps({"alert_id": str(alert_id)}),
            )
            for reviewer in reviewers:
                await send_notification(
                    reviewer["id"],
                    "alert_raised",
                    NotificationEntity("alert", alert_id),
                    {"alert_id": alert_id, "report_id": report_id, "escalation_level": 0},
                    transaction_connection=conn,
                )
            result = await _alert_row(conn, alert_id)
            if result is None:
                raise RuntimeError("alert disappeared after creation")
            return result


async def get_alert(alert_id: UUID, actor: Actor) -> asyncpg.Record:
    """Return one alert only to its reporter or a responding role."""
    if actor.actor_type is not ActorType.HUMAN or actor.profile_id is None or actor.role is None:
        raise AlertError("alert_actor_forbidden", "human profile is required")
    async with connection() as conn:
        row = await _alert_row(conn, alert_id)
    if row is None:
        raise AlertError("alert_not_found", "alert does not exist")
    if actor.role is Role.REPORTER and row["raised_by"] != actor.profile_id:
        raise AlertError("alert_forbidden", "alert belongs to another reporter")
    if actor.role not in {Role.REPORTER, Role.REVIEWER, Role.ADMIN}:
        raise AlertError("alert_forbidden", "role cannot read alerts")
    return row


async def list_alerts(actor: Actor, *, limit: int = 100) -> list[asyncpg.Record]:
    """List live and historical alerts with unacknowledged items first."""
    _require_responder(actor)
    if not 1 <= limit <= 200:
        raise AlertError("alert_limit_invalid", "alert limit is invalid")
    async with connection() as conn:
        return await conn.fetch(
            """
            select
              alerts.*,
              reports.human_ref,
              reports.description_original,
              profiles.display_name as acknowledged_by_name
            from alerts
            join reports on reports.id = alerts.report_id
            left join profiles on profiles.id = alerts.acknowledged_by
            order by
              (alerts.resolution_note is null) desc,
              (alerts.acknowledged_at is null) desc,
              alerts.raised_at desc,
              alerts.id desc
            limit $1
            """,
            limit,
        )


async def acknowledge_alert(alert_id: UUID, actor: Actor) -> asyncpg.Record:
    """Record the first named human acknowledgement and never replace it."""
    responder_id = _require_responder(actor)
    async with connection() as conn:
        async with conn.transaction():
            alert = await conn.fetchrow("select * from alerts where id = $1 for update", alert_id)
            if alert is None:
                raise AlertError("alert_not_found", "alert does not exist")
            if alert["acknowledged_at"] is None:
                await conn.execute(
                    """
                    update alerts
                    set acknowledged_by = $2, acknowledged_at = now()
                    where id = $1
                    """,
                    alert_id,
                    responder_id,
                )
                await conn.execute(
                    """
                    insert into audit_log (
                      report_id, actor_type, actor_id, event, metadata
                    )
                    values ($1, 'human', $2, 'acknowledge_alert', $3::jsonb)
                    """,
                    alert["report_id"],
                    responder_id,
                    json.dumps({"alert_id": str(alert_id)}),
                )
            result = await _alert_row(conn, alert_id)
            if result is None:
                raise RuntimeError("alert disappeared after acknowledgement")
            return result


async def resolve_alert(
    alert_id: UUID,
    actor: Actor,
    *,
    resolution_note: str,
) -> asyncpg.Record:
    """Resolve with a deliberate note and acknowledge simultaneously when needed."""
    responder_id = _require_responder(actor)
    clean_note = resolution_note.strip()
    if not clean_note:
        raise AlertError("alert_resolution_required", "resolution note is required")
    async with connection() as conn:
        async with conn.transaction():
            alert = await conn.fetchrow("select * from alerts where id = $1 for update", alert_id)
            if alert is None:
                raise AlertError("alert_not_found", "alert does not exist")
            if alert["resolution_note"] is None:
                await conn.execute(
                    """
                    update alerts
                    set resolution_note = $2,
                        acknowledged_by = coalesce(acknowledged_by, $3),
                        acknowledged_at = coalesce(acknowledged_at, now())
                    where id = $1
                    """,
                    alert_id,
                    clean_note,
                    responder_id,
                )
                await conn.execute(
                    """
                    insert into audit_log (
                      report_id, actor_type, actor_id, event, metadata
                    )
                    values ($1, 'human', $2, 'resolve_alert', $3::jsonb)
                    """,
                    alert["report_id"],
                    responder_id,
                    json.dumps({"alert_id": str(alert_id)}),
                )
            result = await _alert_row(conn, alert_id)
            if result is None:
                raise RuntimeError("alert disappeared after resolution")
            return result


async def escalate_due_alerts(
    *,
    threshold_minutes: int,
    now: datetime | None = None,
) -> list[UUID]:
    """Escalate each due alert exactly once and notify every reviewer and admin."""
    if threshold_minutes < 1:
        raise AlertError("alert_threshold_invalid", "alert threshold must be positive")
    checked_at = now or datetime.now(timezone.utc)
    cutoff = checked_at - timedelta(minutes=threshold_minutes)
    escalated: list[UUID] = []
    async with connection() as conn:
        async with conn.transaction():
            recipients = await conn.fetch(
                """
                select id
                from profiles
                where role in ('reviewer', 'admin')
                order by id
                """
            )
            if not recipients:
                raise AlertError("alert_no_escalation_recipients", "no escalation recipient exists")
            due = await conn.fetch(
                """
                select *
                from alerts
                where acknowledged_at is null
                  and escalated_at is null
                  and resolution_note is null
                  and raised_at <= $1
                order by raised_at, id
                for update skip locked
                """,
                cutoff,
            )
            for alert in due:
                alert_id = alert["id"]
                await conn.execute(
                    "update alerts set escalated_at = $2 where id = $1",
                    alert_id,
                    checked_at,
                )
                await conn.execute(
                    """
                    insert into audit_log (
                      report_id, actor_type, event, metadata
                    )
                    values ($1, 'system', 'escalate_alert', $2::jsonb)
                    """,
                    alert["report_id"],
                    json.dumps({"alert_id": str(alert_id)}),
                )
                for recipient in recipients:
                    await send_notification(
                        recipient["id"],
                        "alert_raised",
                        NotificationEntity("alert", alert_id),
                        {
                            "alert_id": alert_id,
                            "report_id": alert["report_id"],
                            "escalation_level": 1,
                        },
                        transaction_connection=conn,
                    )
                escalated.append(alert_id)
    return escalated
