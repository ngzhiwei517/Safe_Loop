"""Own the process-wide asyncpg pool used by database-backed services."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from app.config import get_settings

_pool: asyncpg.Pool | None = None


async def init_pool(database_url: str | None = None) -> asyncpg.Pool:
    """Create the shared pool once so services reuse bounded connections."""
    global _pool
    if _pool is None:
        url = database_url or get_settings().database_url
        if not url:
            raise ValueError("DATABASE_URL is required")
        _pool = await asyncpg.create_pool(url)
    return _pool


async def close_pool() -> None:
    """Close the shared pool during application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[PoolConnectionProxy[asyncpg.Record]]:
    """Lease one pool connection and return it even when a service fails."""
    pool = _pool or await init_pool()
    async with pool.acquire() as conn:
        yield conn
