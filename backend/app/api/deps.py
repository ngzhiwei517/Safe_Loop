"""Resolve bearer JWTs; Phase 1 replaces only this dependency's implementation later."""

from __future__ import annotations

import time
from typing import Any, cast
from uuid import UUID

import httpx
import jwt
from fastapi import Header, HTTPException

from app.config import get_settings
from app.domain.enums import ActorType, Role
from app.services.profile_service import get_profile_role
from app.services.report_service import Actor

_profile_cache: dict[UUID, tuple[Role, float]] = {}
_PROFILE_CACHE_SECONDS = 60.0
_jwks_cache: dict[str, tuple[dict[str, dict[str, object]], float]] = {}
_JWKS_CACHE_SECONDS = 600.0
_JWKS_TIMEOUT_SECONDS = 5.0


class _JwksUnavailableError(Exception):
    """Signal that configured Supabase signing keys could not be loaded."""


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


def _parse_jwks(payload: object) -> dict[str, dict[str, object]]:
    if not isinstance(payload, dict):
        raise _JwksUnavailableError
    payload_map = cast(dict[object, object], payload)
    raw_keys = payload_map.get("keys")
    if not isinstance(raw_keys, list):
        raise _JwksUnavailableError

    keys: dict[str, dict[str, object]] = {}
    for raw_key in raw_keys:
        if not isinstance(raw_key, dict):
            continue
        raw_key_map = cast(dict[object, object], raw_key)
        kid = raw_key_map.get("kid")
        if not isinstance(kid, str) or not kid:
            continue
        keys[kid] = {
            name: value
            for name, value in raw_key_map.items()
            if isinstance(name, str)
        }
    if not keys:
        raise _JwksUnavailableError
    return keys


async def _load_project_jwks(supabase_url: str) -> dict[str, dict[str, object]]:
    """Load keys only from the configured project, never a token-provided URL."""
    endpoint = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=_JWKS_TIMEOUT_SECONDS,
        ) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            payload = cast(object, response.json())
    except (httpx.HTTPError, ValueError) as error:
        raise _JwksUnavailableError from error
    return _parse_jwks(payload)


async def _project_jwks(
    supabase_url: str,
    *,
    force_refresh: bool = False,
) -> dict[str, dict[str, object]]:
    now = time.monotonic()
    cached = _jwks_cache.get(supabase_url)
    if not force_refresh and cached is not None and cached[1] > now:
        return cached[0]
    keys = await _load_project_jwks(supabase_url)
    _jwks_cache[supabase_url] = (keys, now + _JWKS_CACHE_SECONDS)
    return keys


async def _es256_signing_key(token_header: dict[str, object], supabase_url: str) -> jwt.PyJWK:
    kid = token_header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise _error(401, "invalid_token", "JWT signing key identifier is invalid")

    try:
        keys = await _project_jwks(supabase_url)
        key_data = keys.get(kid)
        if key_data is None:
            keys = await _project_jwks(supabase_url, force_refresh=True)
            key_data = keys.get(kid)
    except _JwksUnavailableError as error:
        raise _error(503, "auth_unavailable", "Supabase signing keys are unavailable") from error

    if key_data is None:
        raise _error(401, "invalid_token", "JWT signing key is unknown")
    if (
        key_data.get("alg") != "ES256"
        or key_data.get("kty") != "EC"
        or key_data.get("use", "sig") != "sig"
    ):
        raise _error(401, "invalid_token", "JWT signing key is invalid")
    key_ops = key_data.get("key_ops", ["verify"])
    if not isinstance(key_ops, list) or "verify" not in key_ops:
        raise _error(401, "invalid_token", "JWT signing key cannot verify tokens")
    try:
        return jwt.PyJWK.from_dict(cast(dict[str, Any], key_data), algorithm="ES256")
    except (jwt.InvalidKeyError, ValueError) as error:
        raise _error(401, "invalid_token", "JWT signing key is invalid") from error


async def _decode_token(token: str) -> dict[str, object]:
    settings = get_settings()
    try:
        raw_header = jwt.get_unverified_header(token)
        token_header = cast(dict[str, object], raw_header)
        algorithm = token_header.get("alg")
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                raise _error(500, "auth_misconfigured", "Supabase JWT secret is missing")
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience,
                options={"require": ["sub", "aud", "exp"]},
            )
        elif algorithm == "ES256":
            if not settings.supabase_url:
                raise _error(500, "auth_misconfigured", "Supabase URL is missing")
            signing_key = await _es256_signing_key(token_header, settings.supabase_url)
            issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["ES256"],
                audience=settings.supabase_jwt_audience,
                issuer=issuer,
                options={"require": ["sub", "aud", "exp", "iss"]},
            )
        else:
            raise _error(401, "invalid_token", "JWT algorithm is not permitted")
    except jwt.ExpiredSignatureError as error:
        raise _error(401, "token_expired", "JWT has expired") from error
    except jwt.InvalidTokenError as error:
        raise _error(401, "invalid_token", "JWT is invalid") from error
    return cast(dict[str, object], claims)


async def _jwt_actor(authorization: str | None) -> Actor:
    if authorization is None or not authorization.startswith("Bearer "):
        raise _error(401, "bearer_token_required", "a bearer token is required")
    token = authorization[7:].strip()
    if not token:
        raise _error(401, "bearer_token_required", "a bearer token is required")
    claims = await _decode_token(token)
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
