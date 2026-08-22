"""Resolve bearer JWTs; Phase 1 replaces only this dependency's implementation later."""

from __future__ import annotations

import time
from uuid import UUID

import jwt
from fastapi import Header, HTTPException

from app.config import get_settings
from app.domain.enums import ActorType, Role
from app.services.profile_service import get_profile_role
from app.services.report_service import Actor

_profile_cache: dict[UUID, tuple[Role, float]] = {}
_PROFILE_CACHE_SECONDS = 60.0


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, {"code": code, "message": message})


def _debug_actor(user: str | None, role: str | None) -> Actor:
    if user is None or role is None:
        raise _error(401, "debug_headers_required", "debug identity headers are required")
    try:
        profile_id = UUID(user)
        profile_role = Role(role)
    except ValueError as error:
        raise _error(400, "invalid_debug_identity", "debug identity headers are invalid") from error
    return Actor(ActorType.HUMAN, profile_id, profile_role)


async def _jwt_actor(authorization: str | None) -> Actor:
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise _error(500, "auth_misconfigured", "Supabase JWT configuration is missing")
    if authorization is None or not authorization.startswith("Bearer "):
        raise _error(401, "bearer_token_required", "a bearer token is required")
    token = authorization[7:].strip()
    if not token:
        raise _error(401, "bearer_token_required", "a bearer token is required")
    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            options={"require": ["sub", "aud", "exp"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise _error(401, "token_expired", "JWT has expired") from error
    except jwt.InvalidTokenError as error:
        raise _error(401, "invalid_token", "JWT is invalid") from error
    try:
        profile_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as error:
        raise _error(401, "invalid_token_subject", "JWT subject is invalid") from error
    cached = _profile_cache.get(profile_id)
    now = time.monotonic()
    if cached is not None and cached[1] > now:
        profile_role = cached[0]
    else:
        database_role = await get_profile_role(profile_id)
        if database_role is None:
            raise _error(403, "profile_not_found", "JWT subject has no SafeLoop profile")
        profile_role = database_role
        _profile_cache[profile_id] = (profile_role, now + _PROFILE_CACHE_SECONDS)
    return Actor(ActorType.HUMAN, profile_id, profile_role)


async def current_actor(
    authorization: str | None = Header(default=None),
    x_debug_user: str | None = Header(default=None),
    x_debug_role: str | None = Header(default=None),
) -> Actor:
    """Use debug headers only in local mode; all other requests require Supabase JWTs."""
    settings = get_settings()
    if settings.app_env == "local" and settings.allow_debug_auth:
        if authorization is None:
            return _debug_actor(x_debug_user, x_debug_role)
    return await _jwt_actor(authorization)
