"""Provide Phase 0 debug authentication; Phase 1 swaps this for JWT verification without changing callers."""

from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException

from app.config import get_settings
from app.domain.enums import ActorType, Role
from app.services.report_service import Actor


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, {"code": code, "message": message})


async def current_actor(
    x_debug_user: str | None = Header(default=None),
    x_debug_role: str | None = Header(default=None),
) -> Actor:
    """Resolve the temporary local actor; Phase 1 replaces only this dependency with JWT verification."""
    settings = get_settings()
    if not settings.allow_debug_auth:
        raise _error(501, "debug_auth_disabled", "debug authentication is disabled")
    if x_debug_user is None or x_debug_role is None:
        raise _error(401, "debug_headers_required", "debug identity headers are required")
    try:
        profile_id = UUID(x_debug_user)
        role = Role(x_debug_role)
    except ValueError as error:
        raise _error(400, "invalid_debug_identity", "debug identity headers are invalid") from error
    return Actor(actor_type=ActorType.HUMAN, profile_id=profile_id, role=role)
