"""Persist reports and centralise every legal status transition."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db import connection
from app.domain.enums import ActorType, ReportStatus, Role
from app.domain.transitions import TransitionError, assert_can


@dataclass(frozen=True)
class Actor:
    """Identify the principal responsible for a database mutation."""

    actor_type: ActorType
    profile_id: UUID | None = None
    role: Role | None = None

    @classmethod
    def ai(cls) -> "Actor":
        """Construct the model actor, which has no human profile."""
        return cls(ActorType.AI)

    @classmethod
    def system(cls) -> "Actor":
        """Construct the trusted orchestration actor."""
        return cls(ActorType.SYSTEM)


async def create_report(
    reporter_id: UUID,
    description_original: str,
    *,
    lang_original: str = "en",
    urgency: str = "medium",
    location_text: str | None = None,
    activity: str | None = None,
    is_confidential: bool = False,
) -> UUID:
    """Create a draft; the database trigger assigns its human reference."""
    async with connection() as conn:
        async with conn.transaction():
            report_id = await conn.fetchval(
                """
                INSERT INTO reports (
                  reporter_id, description_original, lang_original, urgency,
                  location_text, activity, is_confidential
                )
                VALUES ($1, $2, $3, $4::urgency, $5, $6, $7)
                RETURNING id
                """,
                reporter_id,
                description_original,
                lang_original,
                urgency,
                location_text,
                activity,
                is_confidential,
            )
            await conn.execute(
                """
                INSERT INTO audit_log (report_id, actor_type, actor_id, event, target, metadata)
                VALUES ($1, 'human', $2, 'create_report', 'draft', '{}'::jsonb)
                """,
                report_id,
                reporter_id,
            )
    if not isinstance(report_id, UUID):
        raise RuntimeError("database returned an invalid report id")
    return report_id


async def get_report(report_id: UUID) -> asyncpg.Record | None:
    """Read one report without introducing a second state-writing path."""
    async with connection() as conn:
        return await conn.fetchrow("SELECT * FROM reports WHERE id = $1", report_id)


async def get_timeline(report_id: UUID) -> list[asyncpg.Record]:
    """Read the immutable report audit trail in chronological order."""
    async with connection() as conn:
        return await conn.fetch(
            "SELECT * FROM audit_log WHERE report_id = $1 ORDER BY created_at, id",
            report_id,
        )


async def transition_report(
    report_id: UUID,
    target: ReportStatus,
    actor: Actor,
    *,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> asyncpg.Record:
    """Apply one state-machine edge and its audit row in one transaction."""
    async with connection() as conn:
        try:
            async with conn.transaction():
                report = await conn.fetchrow(
                    "SELECT * FROM reports WHERE id = $1 FOR UPDATE", report_id
                )
                if report is None:
                    raise TransitionError("illegal_transition", "report does not exist")

                source = ReportStatus(report["status"])
                transition = assert_can(source, target, actor.actor_type, actor.role, reason)
                await conn.execute(
                    "SELECT set_config('safeloop.actor_type', $1, true)",
                    actor.actor_type.value,
                )
                await conn.execute(
                    """
                    UPDATE reports
                    SET status = $2::report_status,
                        submitted_at = CASE WHEN $2::report_status = 'submitted'
                          THEN COALESCE(submitted_at, now()) ELSE submitted_at END,
                        closed_at = CASE WHEN $2::report_status = 'verified_closed'
                          THEN COALESCE(closed_at, now()) ELSE closed_at END
                    WHERE id = $1
                    """,
                    report_id,
                    target.value,
                )
                await conn.execute(
                    """
                    INSERT INTO audit_log (
                      report_id, actor_type, actor_id, event, source, target, reason, metadata
                    )
                    VALUES ($1, $2::actor_type, $3, $4, $5::report_status,
                            $6::report_status, $7, $8::jsonb)
                    """,
                    report_id,
                    actor.actor_type.value,
                    actor.profile_id,
                    transition.event,
                    source.value,
                    target.value,
                    reason,
                    json.dumps(metadata or {}),
                )
                result = await conn.fetchrow("SELECT * FROM reports WHERE id = $1", report_id)
                if result is None:
                    raise RuntimeError("report disappeared after transition")
                return result
        except asyncpg.InsufficientPrivilegeError as error:
            raise TransitionError("database_guard", "database guard rejected transition") from error
