"""Expose the minimal health endpoint used to verify the backend is running."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.briefings import router as briefings_router
from app.api.documents import router as documents_router
from app.api.metrics import router as metrics_router
from app.api.notifications import router as notifications_router
from app.config import get_settings
from app.api.reports import router as reports_router
from app.db import close_pool
from app.domain.transitions import TRANSITIONS
from app.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Own the scheduler and database pool for exactly one application process."""
    scheduler = start_scheduler()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await close_pool()


app = FastAPI(lifespan=lifespan)
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
app.include_router(briefings_router)
app.include_router(documents_router)
app.include_router(metrics_router)


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
