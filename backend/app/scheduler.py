"""Schedule database-backed maintenance without creating a second delivery path."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from app.config import get_settings
from app.services.overdue_service import send_daily_overdue_notifications

OVERDUE_JOB_ID = "daily-overdue-notifications"


def build_scheduler() -> AsyncIOScheduler:
    """Build the site-timezone cron schedule without starting background work."""
    settings = get_settings()
    site_timezone = ZoneInfo(settings.site_timezone)
    scheduler = AsyncIOScheduler(timezone=site_timezone)
    scheduler.add_job(
        send_daily_overdue_notifications,
        CronTrigger(
            hour=settings.overdue_notification_hour,
            minute=0,
            timezone=site_timezone,
        ),
        id=OVERDUE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=12 * 60 * 60,
    )
    return scheduler


def start_scheduler() -> AsyncIOScheduler | None:
    """Start jobs only for a process configured with a database."""
    if not get_settings().database_url:
        return None
    scheduler = build_scheduler()
    scheduler.start()
    return scheduler
