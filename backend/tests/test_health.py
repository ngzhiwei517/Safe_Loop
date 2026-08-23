"""Verify the minimal health contract without network or database access."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import main as main_module
from app.health import DeepHealth
from app.main import app


def test_health_returns_ok() -> None:
    """The process exposes a successful health response."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_frontend_origin_is_allowed() -> None:
    """The browser can call the API without opening CORS to arbitrary origins."""
    response = TestClient(app).options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


@pytest.mark.parametrize(("healthy", "status_code"), [(True, 200), (False, 503)])
def test_deep_health_uses_dependency_result_for_http_status(
    monkeypatch: pytest.MonkeyPatch,
    healthy: bool,
    status_code: int,
) -> None:
    async def fake_deep_health() -> DeepHealth:
        return {
            "ok": healthy,
            "checks": {
                "database": {"ok": healthy, "code": "ok", "latency_ms": 1.0}
            },
        }

    monkeypatch.setattr(main_module, "run_deep_health", fake_deep_health)
    response = TestClient(app).get("/health/deep")

    assert response.status_code == status_code
    assert response.json()["ok"] is healthy


def test_generated_frontend_state_machine_matches_the_server_contract() -> None:
    """A frontend build must never silently replace server transitions with an empty table."""
    response = TestClient(app).get("/state-machine")
    generated = (
        Path(__file__).resolve().parents[2] / "frontend" / "lib" / "stateMachine.ts"
    ).read_text(encoding="utf-8")
    payload = generated.split("export const stateMachine = ", 1)[1].split(
        " as const;\nexport type StateMachineTransition",
        1,
    )[0]

    assert response.status_code == 200
    assert json.loads(payload) == response.json()
