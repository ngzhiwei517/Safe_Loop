"""Issue idempotent daily reminders through the existing notification seam."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db import connection
from app.services.notification_service import NotificationEntity, send_notification


async def send_daily_overdue_notifications(
    *,
    as_of: datetime | None = None,
    delivery_date: date | None = None,
) -> int:
    """Notify each overdue assignee once for the site's current calendar day."""
    current_time = as_of or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    current_delivery_date = delivery_date or current_time.astimezone(
        ZoneInfo(get_settings().site_timezone)
    ).date()

    async with connection() as conn:
        async with conn.transaction():
            overdue_actions = await conn.fetch(
                """
                select
                  action.id as corrective_action_id,
                  action.report_id,
                  action.rework_count::integer,
                  assignment.id as assignment_id,
                  assignment.assignee_id
                from corrective_actions action
                join report_assignments assignment
                  on assignment.id = action.assignment_id
                 and assignment.report_id = action.report_id
                 and assignment.active
                join reports report on report.id = action.report_id
                where action.status = 'assigned'::action_status
                  and action.due_at < $1
                  and report.status = 'action_assigned'::report_status
                order by action.due_at, action.id
                """,
                current_time,
            )
            for action in overdue_actions:
                await send_notification(
                    action["assignee_id"],
                    "overdue",
                    NotificationEntity(
                        "corrective_action",
                        action["corrective_action_id"],
                    ),
                    {
                        "report_id": action["report_id"],
                        "assignment_id": action["assignment_id"],
                        "corrective_action_id": action["corrective_action_id"],
                        "rework_count": action["rework_count"],
                    },
                    transaction_connection=conn,
                    delivery_date=current_delivery_date,
                )
    return len(overdue_actions)
