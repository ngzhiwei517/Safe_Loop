"""Expose the minimal health endpoint used to verify the backend is running."""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.api.reports import router as reports_router
from app.domain.transitions import TRANSITIONS

app = FastAPI()
app.include_router(reports_router)


@app.get("/health")
async def health() -> dict[str, object]:
    """Report process health and the configured application environment."""
    return {"ok": True, "env": get_settings().app_env}


@app.get("/state-machine")
async def state_machine() -> list[dict[str, object]]:
    """Expose the server-owned transition table to clients and contract tests."""
    return [
        {
            "event": transition.event,
            "source": transition.source.value,
            "target": transition.target.value,
            "actor_types": sorted(actor.value for actor in transition.actor_types),
            "roles": sorted(role.value for role in transition.roles),
            "requires_reason": transition.requires_reason,
            "note": transition.note,
        }
        for transition in TRANSITIONS
    ]
