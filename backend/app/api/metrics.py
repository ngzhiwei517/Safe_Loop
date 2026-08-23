"""Expose reviewer metrics as machine data with explicit units."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder

from app.api.deps import current_actor
from app.domain.enums import ActorType, Role
from app.observability import operational_snapshot
from app.services.metrics_service import MetricsError, get_metrics_summary
from app.services.report_service import Actor

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/operational")
async def operational_metrics(
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Expose bounded process metrics only to human operations roles."""
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.role not in {Role.REVIEWER, Role.ADMIN}
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "code": "metrics_actor_forbidden",
                "message": "reviewer or admin profile is required",
            },
        )
    return cast(dict[str, object], operational_snapshot())


@router.get("/summary")
async def metrics_summary(actor: Actor = Depends(current_actor)) -> dict[str, object]:
    """Return an authorized operational snapshot without presentation strings."""
    try:
        summary = await get_metrics_summary(actor)
    except MetricsError as error:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {"code": error.code, "message": error.message},
        ) from error
    return cast(dict[str, object], jsonable_encoder(asdict(summary)))
