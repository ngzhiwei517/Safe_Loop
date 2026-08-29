"""Verify database-pool settings shared by every backend service."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from app import db


def test_pool_disables_prepared_statement_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supabase transaction pooling must not reuse connection-local statements."""
    sentinel = object()
    calls: list[tuple[str, int]] = []

    async def create_pool(url: str, *, statement_cache_size: int) -> object:
        calls.append((url, statement_cache_size))
        return sentinel

    monkeypatch.setattr(asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(db, "_pool", None)

    pool = asyncio.run(db.init_pool("postgresql://example.test/postgres"))

    assert pool is sentinel
    assert calls == [("postgresql://example.test/postgres", 0)]
