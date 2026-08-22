"""Escalate silent urgent alerts from a scheduler without adding a queue dependency."""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.db import close_pool, init_pool
from app.services.alert_service import escalate_due_alerts


async def run() -> int:
    """Run one idempotent escalation pass and return how many alerts changed."""
    settings = get_settings()
    await init_pool()
    try:
        alert_ids = await escalate_due_alerts(
            threshold_minutes=settings.alert_escalate_minutes,
        )
        return len(alert_ids)
    finally:
        await close_pool()


def main() -> None:
    """Provide a cron-friendly module entry point."""
    count = asyncio.run(run())
    print(f"escalated_alerts={count}")


if __name__ == "__main__":
    main()
