"""Apply the deterministic demo dataset without exposing database credentials."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg


async def _apply() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    root = Path(__file__).resolve().parents[1]
    sql = (root / "supabase" / "demo_seed.sql").read_text(encoding="utf-8")
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(sql)
        summary = await connection.fetchrow(
            """
            select
              count(*)::integer as report_count,
              count(distinct status)::integer as status_count
            from public.reports
            where id::text like '61000000-0000-4000-8000-%'
            """
        )
    finally:
        await connection.close()
    if summary is None:
        raise RuntimeError("demo seed did not return a summary")
    print(
        "Demo seed ready: "
        f"{summary['report_count']} reports across {summary['status_count']} statuses."
    )


if __name__ == "__main__":
    asyncio.run(_apply())
