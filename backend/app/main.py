"""Expose the minimal health endpoint used to verify the backend is running."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.notifications import router as notifications_router
from app.config import get_settings
from app.api.reports import router as reports_router
from app.domain.transitions import TRANSITIONS

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in get_settings().frontend_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Debug-Role", "X-Debug-User"],
)
app.include_router(reports_router)
app.include_router(notifications_router)
app.include_router(alerts_router)


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
