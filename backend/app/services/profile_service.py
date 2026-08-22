"""Load profile identity data needed after a JWT has been verified."""

from __future__ import annotations

from uuid import UUID

from app.db import connection
from app.domain.enums import Role


async def get_profile_role(profile_id: UUID) -> Role | None:
    """Return the database-owned role for a token subject."""
    async with connection() as conn:
        value = await conn.fetchval("SELECT role::text FROM profiles WHERE id = $1", profile_id)
    return Role(value) if value is not None else None
