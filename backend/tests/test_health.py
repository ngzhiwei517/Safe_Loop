"""Verify the minimal health contract without network or database access."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    """The process exposes a successful health response."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True
