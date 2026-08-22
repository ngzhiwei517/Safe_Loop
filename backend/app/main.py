"""Expose the minimal health endpoint used to verify the backend is running."""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings

app = FastAPI()


@app.get("/health")
async def health() -> dict[str, object]:
    """Report process health and the configured application environment."""
    return {"ok": True, "env": get_settings().app_env}
