"""Enforce fixed-window request limits consistently across backend workers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil

from app.db import connection


class RateLimitExceeded(Exception):
    """Carry a machine scope and an exact retry delay to the HTTP boundary."""

    def __init__(self, scope: str, retry_after_seconds: int) -> None:
        super().__init__(scope)
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


def subject_hash(subject: str) -> str:
    """Keep profile IDs and client addresses out of the limiter table."""
    return sha256(subject.encode("utf-8")).hexdigest()


async def consume_rate_limit(
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int = 60,
    now: datetime | None = None,
) -> None:
    """Atomically consume one slot in a database-shared fixed window."""
    if not scope.strip() or not subject or limit < 1 or window_seconds < 1:
        raise ValueError("rate limit configuration is invalid")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("rate limit time must be timezone-aware")
    epoch_seconds = int(current.timestamp())
    window_epoch = epoch_seconds - epoch_seconds % window_seconds
    window_started_at = datetime.fromtimestamp(window_epoch, tz=UTC)
    window_ends_at = window_started_at + timedelta(seconds=window_seconds)

    async with connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                delete from request_rate_limits
                where window_started_at < now() - interval '2 hours'
                """
            )
            count = await conn.fetchval(
                """
                insert into request_rate_limits (
                  scope, subject_hash, window_started_at, request_count
                )
                values ($1, $2, $3, 1)
                on conflict (scope, subject_hash, window_started_at) do update
                  set request_count = request_rate_limits.request_count + 1
                  where request_rate_limits.request_count < $4
                returning request_count
                """,
                scope,
                subject_hash(subject),
                window_started_at,
                limit,
            )
    if count is None:
        retry_after = max(1, ceil((window_ends_at - current).total_seconds()))
        raise RateLimitExceeded(scope, retry_after)
    if not isinstance(count, int):
        raise RuntimeError("database returned an invalid rate-limit count")
