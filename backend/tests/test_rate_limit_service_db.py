"""Prove the shared Postgres limiter is atomic and stores no raw identity."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import UTC, datetime
import os
from typing import Any, TypeVar

import pytest

from app.db import close_pool, connection, init_pool
from app.services.rate_limit_service import (
    RateLimitExceeded,
    consume_rate_limit,
    subject_hash,
)

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
T = TypeVar("T")
_test_loop: asyncio.AbstractEventLoop | None = None


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    global _test_loop
    assert DATABASE_URL is not None
    _test_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_test_loop)
    _test_loop.run_until_complete(init_pool(DATABASE_URL))
    yield
    _test_loop.run_until_complete(close_pool())
    _test_loop.close()
    _test_loop = None
    asyncio.set_event_loop(None)


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    assert _test_loop is not None
    return _test_loop.run_until_complete(coroutine)


def test_shared_limit_refuses_the_first_request_above_threshold() -> None:
    subject = "rate-limit-db-fixture"
    moment = datetime.now(UTC).replace(second=3, microsecond=0)

    async def exercise() -> None:
        async with connection() as conn:
            await conn.execute(
                "delete from request_rate_limits where subject_hash = $1",
                subject_hash(subject),
            )
        try:
            await consume_rate_limit(
                scope="report_submission",
                subject=subject,
                limit=2,
                now=moment,
            )
            await consume_rate_limit(
                scope="report_submission",
                subject=subject,
                limit=2,
                now=moment,
            )
            with pytest.raises(RateLimitExceeded) as error:
                await consume_rate_limit(
                    scope="report_submission",
                    subject=subject,
                    limit=2,
                    now=moment,
                )
            assert error.value.retry_after_seconds == 57
            async with connection() as conn:
                row = await conn.fetchrow(
                    """
                    select subject_hash, request_count
                    from request_rate_limits
                    where scope = 'report_submission' and subject_hash = $1
                    """,
                    subject_hash(subject),
                )
            assert row is not None
            assert row["subject_hash"] != subject
            assert row["request_count"] == 2
        finally:
            async with connection() as conn:
                await conn.execute(
                    "delete from request_rate_limits where subject_hash = $1",
                    subject_hash(subject),
                )

    run(exercise())
