"""Verify the minimal health contract without network or database access."""

from __future__ import annotations

from fastapi.testclient import TestClient

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
