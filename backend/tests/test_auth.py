"""Test JWT authentication and the environment-gated debug fallback."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest

from app.api import deps
from app.config import get_settings
from app.domain.enums import Role

SECRET = "test-secret"
PROFILE_ID = UUID("00000000-0000-0000-0000-000000000003")


def token(*, expires_delta: timedelta = timedelta(minutes=5)) -> str:
    return jwt.encode(
        {
            "sub": str(PROFILE_ID),
            "aud": "authenticated",
            "exp": datetime.now(timezone.utc) + expires_delta,
        },
        SECRET,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    get_settings.cache_clear()
    deps._profile_cache.clear()
    yield
    get_settings.cache_clear()
    deps._profile_cache.clear()


async def profile_role(_: UUID) -> Role:
    return Role.REVIEWER


def test_valid_token_resolves_database_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(deps, "get_profile_role", profile_role)
    actor = asyncio.run(deps.current_actor(f"Bearer {token()}"))
    assert actor.profile_id == PROFILE_ID
    assert actor.role == Role.REVIEWER


def test_expired_token_returns_401() -> None:
    with pytest.raises(Exception) as error:
        asyncio.run(deps.current_actor(f"Bearer {token(expires_delta=timedelta(seconds=-1))}"))
    assert error.value.status_code == 401
    assert error.value.detail["code"] == "token_expired"


def test_debug_headers_are_impossible_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(Exception) as error:
        asyncio.run(
            deps.current_actor(
                None,
                "00000000-0000-0000-0000-000000000001",
                "reporter",
            )
        )
    assert error.value.status_code == 401
    assert error.value.detail["code"] == "bearer_token_required"


def test_debug_headers_work_only_in_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ALLOW_DEBUG_AUTH", "true")
    actor = asyncio.run(
        deps.current_actor(
            None,
            "00000000-0000-0000-0000-000000000001",
            "reporter",
        )
    )
    assert actor.role == Role.REPORTER
