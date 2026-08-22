"""Test JWT authentication and the environment-gated debug fallback."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.api import deps
from app.config import get_settings
from app.domain.enums import Role

SECRET = "test-secret"
PROFILE_ID = UUID("00000000-0000-0000-0000-000000000003")
SUPABASE_URL = "https://test-project.supabase.co"
ES256_KID = "test-es256-key"
ES256_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


def es256_jwk() -> dict[str, object]:
    raw_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(ES256_PRIVATE_KEY.public_key()))
    jwk = cast(dict[str, object], raw_jwk)
    jwk.update({"kid": ES256_KID, "alg": "ES256", "use": "sig", "key_ops": ["verify"]})
    return jwk


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


def es256_token(*, kid: str = ES256_KID) -> str:
    return jwt.encode(
        {
            "sub": str(PROFILE_ID),
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        ES256_PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": kid, "jku": "http://127.0.0.1/private-jwks"},
    )


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    get_settings.cache_clear()
    deps._profile_cache.clear()
    deps._jwks_cache.clear()
    yield
    get_settings.cache_clear()
    deps._profile_cache.clear()
    deps._jwks_cache.clear()


async def profile_role(_: UUID) -> Role:
    return Role.REVIEWER


def test_valid_token_resolves_database_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(deps, "get_profile_role", profile_role)
    actor = asyncio.run(deps.current_actor(f"Bearer {token()}"))
    assert actor.profile_id == PROFILE_ID
    assert actor.role == Role.REVIEWER


def test_es256_token_uses_configured_project_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded_urls: list[str] = []

    async def load_jwks(supabase_url: str) -> dict[str, dict[str, object]]:
        loaded_urls.append(supabase_url)
        return {ES256_KID: es256_jwk()}

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(deps, "_load_project_jwks", load_jwks)
    monkeypatch.setattr(deps, "get_profile_role", profile_role)
    actor = asyncio.run(deps.current_actor(f"Bearer {es256_token()}"))

    assert actor.profile_id == PROFILE_ID
    assert actor.role == Role.REVIEWER
    assert loaded_urls == [SUPABASE_URL]


def test_es256_unknown_kid_refreshes_then_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    load_count = 0

    async def load_jwks(_: str) -> dict[str, dict[str, object]]:
        nonlocal load_count
        load_count += 1
        return {ES256_KID: es256_jwk()}

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(deps, "_load_project_jwks", load_jwks)

    with pytest.raises(Exception) as error:
        asyncio.run(deps.current_actor(f"Bearer {es256_token(kid='unknown-key')}"))

    assert error.value.status_code == 401
    assert error.value.detail["code"] == "invalid_token"
    assert load_count == 2


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
