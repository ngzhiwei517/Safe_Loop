"""Submit corrective-action proof and its report transition atomically."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg

from app.db import connection
from app.domain.enums import ActionStatus, ActorType, MediaPhase, ReportStatus, Role
from app.services.report_service import (
    Actor,
    TranscriptConfirmationError,
    confirm_transcript_text,
    transition_report,
)


class ActionError(Exception):
    """Carry a stable action API code without user-facing prose."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ActionSubmissionResult:
    """Return the records committed by one evidence submission."""

    action: asyncpg.Record
    report: asyncpg.Record
    media_ids: tuple[UUID, ...]


def _submission_values(
    actor: Actor,
    completed_note: str | None,
    media_ids: list[UUID],
) -> tuple[str | None, tuple[UUID, ...]]:
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.profile_id is None
        or actor.role is not Role.RESPONSIBLE
    ):
        raise ActionError(
            "action_actor_forbidden",
            "action submission requires a responsible human profile",
        )
    clean_note = completed_note.strip() if completed_note is not None else None
    if not clean_note:
        clean_note = None
    unique_media_ids = tuple(dict.fromkeys(media_ids))
    if len(unique_media_ids) != len(media_ids):
        raise ActionError("action_media_invalid", "evidence media ids must be unique")
    if clean_note is None and not unique_media_ids:
        raise ActionError(
            "action_evidence_required",
            "action submission requires a completed note or evidence media",
        )
    return clean_note, unique_media_ids


async def submit_action(
    report_id: UUID,
    action_id: UUID,
    actor: Actor,
    *,
    completed_note: str | None,
    media_ids: list[UUID],
    transcript_id: UUID | None = None,
) -> ActionSubmissionResult:
    """Attach fresh proof, mark the action submitted, and transition in one commit."""
    clean_note, unique_media_ids = _submission_values(actor, completed_note, media_ids)
    if actor.profile_id is None:
        raise RuntimeError("validated responsible actor has no profile id")

    async with connection() as conn:
        async with conn.transaction():
            report = await conn.fetchrow(
                "select id, status::text from reports where id = $1 for update",
                report_id,
            )
            if report is None:
                raise ActionError("action_not_found", "action report does not exist")

            action = await conn.fetchrow(
                """
                select
                  action.*,
                  assignment.assignee_id,
                  assignment.active
                from corrective_actions action
                join report_assignments assignment
                  on assignment.id = action.assignment_id
                 and assignment.report_id = action.report_id
                where action.id = $1 and action.report_id = $2
                for update of action, assignment
                """,
                action_id,
                report_id,
            )
            if action is None:
                raise ActionError("action_not_found", "corrective action does not exist")
            if not action["active"] or action["assignee_id"] != actor.profile_id:
                raise ActionError("action_forbidden", "action belongs to another assignee")
            if (
                action["status"] != ActionStatus.ASSIGNED.value
                or report["status"] != ReportStatus.ACTION_ASSIGNED.value
            ):
                raise ActionError(
                    "action_not_submittable",
                    "corrective action is not accepting evidence",
                )

            if clean_note is None and transcript_id is not None:
                raise ActionError(
                    "action_transcript_not_found",
                    "a transcript requires a confirmed completion note",
                )
            if clean_note is not None:
                try:
                    await confirm_transcript_text(
                        conn,
                        report_id=report_id,
                        transcript_id=transcript_id,
                        confirmed_text=clean_note,
                        context="action_completion",
                        context_id=action_id,
                    )
                except TranscriptConfirmationError as error:
                    raise ActionError(
                        "action_transcript_not_found", str(error)
                    ) from error

            if unique_media_ids:
                media_rows = await conn.fetch(
                    """
                    select id, report_id, storage_path, phase::text, corrective_action_id
                    from report_media
                    where id = any($1::uuid[])
                    for update
                    """,
                    list(unique_media_ids),
                )
                valid_ids = {
                    row["id"]
                    for row in media_rows
                    if row["report_id"] == report_id
                    and row["storage_path"].startswith(
                        f"{actor.profile_id}/{report_id}/"
                    )
                    and row["phase"] == MediaPhase.EVIDENCE.value
                    and row["corrective_action_id"] is None
                }
                if valid_ids != set(unique_media_ids):
                    raise ActionError(
                        "action_media_invalid",
                        "evidence media must be new and belong to this report",
                    )
                await conn.execute(
                    """
                    update report_media
                    set corrective_action_id = $2
                    where id = any($1::uuid[])
                    """,
                    list(unique_media_ids),
                    action_id,
                )

            submitted_action = await conn.fetchrow(
                """
                update corrective_actions
                set status = 'submitted'::action_status,
                    completed_note = $2,
                    submitted_at = now()
                where id = $1
                returning *
                """,
                action_id,
                clean_note,
            )
            if submitted_action is None:
                raise RuntimeError("corrective action disappeared while submitting")

            transitioned = await transition_report(
                report_id,
                ReportStatus.ACTION_SUBMITTED,
                actor,
                metadata={
                    "corrective_action_id": str(action_id),
                    "completed_note": clean_note,
                    "media_ids": [str(media_id) for media_id in unique_media_ids],
                },
                transaction_connection=conn,
            )
            return ActionSubmissionResult(
                submitted_action,
                transitioned,
                unique_media_ids,
            )
