"""Commit reviewer verification evidence and the rework transition together."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from uuid import UUID

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from app.db import connection
from app.domain.enums import ActionStatus, ActorType, ReportStatus, Role
from app.services.notification_service import NotificationEntity, send_notification
from app.services.report_service import Actor, transition_report

Checklist = dict[str, object] | list[object]


class VerificationError(Exception):
    """Carry a stable verification API code without user-facing prose."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VerificationResult:
    """Return all records changed by one atomic verification decision."""

    verification: asyncpg.Record
    report: asyncpg.Record
    action: asyncpg.Record
    assignment: asyncpg.Record


_VAGUE_REASONS = frozenset(
    {
        "incomplete",
        "not complete",
        "not done",
        "not done yet",
        "still not done",
        "未完成",
        "没完成",
        "没做",
    }
)


def _normalise_reason(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).strip()


def _verification_values(
    actor: Actor,
    *,
    passed: bool,
    notes: str,
    reason: str | None,
    new_due_at: datetime | None,
) -> tuple[str, str | None, datetime | None]:
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.profile_id is None
        or actor.role is not Role.REVIEWER
    ):
        raise VerificationError(
            "verification_actor_forbidden",
            "verification requires a reviewer human profile",
        )

    clean_notes = notes.strip()
    if not clean_notes:
        raise VerificationError(
            "verification_notes_required",
            "verification notes are required",
        )

    clean_reason = reason.strip() if reason is not None else None
    if not passed:
        if not clean_reason:
            raise VerificationError(
                "verification_reason_required",
                "failed verification requires a specific deficiency",
            )
        if _normalise_reason(clean_reason) in _VAGUE_REASONS:
            raise VerificationError(
                "verification_reason_too_vague",
                "failed verification reason must identify the deficiency",
            )
        if new_due_at is None:
            raise VerificationError(
                "verification_due_at_required",
                "failed verification requires a new due date",
            )
        if new_due_at.tzinfo is None or new_due_at.utcoffset() is None:
            raise VerificationError(
                "verification_due_at_invalid",
                "verification due date needs a timezone",
            )
    return clean_notes, clean_reason, new_due_at if not passed else None


async def _create_closure_receipt(
    conn: PoolConnectionProxy[asyncpg.Record],
    *,
    report: asyncpg.Record,
    action: asyncpg.Record,
    verification: asyncpg.Record,
    reviewer_id: UUID,
    verification_notes: str,
) -> asyncpg.Record:
    """Snapshot only facts present in the human-verified case."""
    reviewer = await conn.fetchrow(
        """
        select coalesce(nullif(btrim(display_name), ''), role::text) as display_name
        from profiles
        where id = $1
        """,
        reviewer_id,
    )
    if reviewer is None:
        raise RuntimeError("verified reviewer profile disappeared")

    before_media = await conn.fetchrow(
        """
        select id
        from report_media
        where report_id = $1 and phase = 'original'::media_phase
        order by created_at, id
        limit 1
        """,
        report["id"],
    )
    after_media = await conn.fetchrow(
        """
        with latest_submission as (
          select metadata
          from audit_log
          where report_id = $1 and event = 'submit_evidence'
          order by created_at desc, id desc
          limit 1
        ), submitted_media as (
          select media_ref.value as media_id, media_ref.ordinality
          from latest_submission
          cross join lateral jsonb_array_elements_text(
            case
              when jsonb_typeof(metadata -> 'media_ids') = 'array'
                then metadata -> 'media_ids'
              else '[]'::jsonb
            end
          ) with ordinality as media_ref(value, ordinality)
        )
        select media.id
        from submitted_media
        join report_media media on media.id::text = submitted_media.media_id
        where media.report_id = $1
          and media.corrective_action_id = $2
          and media.phase = 'evidence'::media_phase
        order by submitted_media.ordinality
        limit 1
        """,
        report["id"],
        action["id"],
    )
    before_media_id = before_media["id"] if before_media is not None else None
    after_media_id = after_media["id"] if after_media is not None else None
    if before_media_id is None or after_media_id is None:
        before_media_id = None
        after_media_id = None

    receipt = await conn.fetchrow(
        """
        insert into closure_receipts (
          report_id, verification_id, corrective_action_id,
          reporter_id, reporter_locale, action_text, verification_notes,
          verified_by_id, verified_by_name, before_media_id, after_media_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        returning *
        """,
        report["id"],
        verification["id"],
        action["id"],
        report["reporter_id"],
        report["reporter_locale"],
        action["action_text"],
        verification_notes,
        reviewer_id,
        reviewer["display_name"],
        before_media_id,
        after_media_id,
    )
    if receipt is None:
        raise RuntimeError("database did not return closure receipt")
    return receipt


async def verify_report(
    report_id: UUID,
    actor: Actor,
    *,
    passed: bool,
    checklist: Checklist | None,
    notes: str,
    reason: str | None = None,
    new_due_at: datetime | None = None,
) -> VerificationResult:
    """Append verification evidence and perform its state transition in one commit."""
    clean_notes, clean_reason, clean_due_at = _verification_values(
        actor,
        passed=passed,
        notes=notes,
        reason=reason,
        new_due_at=new_due_at,
    )
    if actor.profile_id is None:
        raise RuntimeError("validated reviewer actor has no profile id")

    async with connection() as conn:
        async with conn.transaction():
            report = await conn.fetchrow(
                """
                select
                  report.id,
                  report.reporter_id,
                  report.status::text,
                  report.closed_at,
                  reporter.preferred_lang as reporter_locale
                from reports report
                join profiles reporter on reporter.id = report.reporter_id
                where report.id = $1
                for update of report
                """,
                report_id,
            )
            if report is None:
                raise VerificationError("verification_not_found", "report does not exist")
            if report["status"] != ReportStatus.ACTION_SUBMITTED.value:
                raise VerificationError(
                    "verification_not_ready",
                    "report is not awaiting verification",
                )

            action = await conn.fetchrow(
                """
                select
                  corrective_action.*,
                  assignment.assignee_id,
                  assignment.active,
                  assignment.due_at as assignment_due_at
                from corrective_actions corrective_action
                join report_assignments assignment
                  on assignment.id = corrective_action.assignment_id
                 and assignment.report_id = corrective_action.report_id
                where corrective_action.report_id = $1
                  and assignment.active
                order by corrective_action.created_at desc, corrective_action.id desc
                limit 1
                for update of corrective_action, assignment
                """,
                report_id,
            )
            if action is None:
                raise VerificationError(
                    "verification_action_not_found",
                    "active corrective action does not exist",
                )
            if action["status"] != ActionStatus.SUBMITTED.value:
                raise VerificationError(
                    "verification_not_ready",
                    "corrective action is not awaiting verification",
                )

            verification = await conn.fetchrow(
                """
                insert into verifications (
                  report_id, corrective_action_id, reviewer_id,
                  passed, checklist, notes, reason, new_due_at
                )
                values ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                returning *
                """,
                report_id,
                action["id"],
                actor.profile_id,
                passed,
                json.dumps(checklist) if checklist is not None else None,
                clean_notes,
                clean_reason if not passed else None,
                clean_due_at,
            )
            if verification is None:
                raise RuntimeError("database did not return verification")

            if passed:
                updated_action = await conn.fetchrow(
                    """
                    update corrective_actions
                    set status = 'verified'::action_status
                    where id = $1
                    returning *
                    """,
                    action["id"],
                )
                if updated_action is None:
                    raise RuntimeError("corrective action disappeared during verification")
                receipt = await _create_closure_receipt(
                    conn,
                    report=report,
                    action=action,
                    verification=verification,
                    reviewer_id=actor.profile_id,
                    verification_notes=clean_notes,
                )
                await send_notification(
                    report["reporter_id"],
                    "report_closed",
                    NotificationEntity("report", report_id),
                    {
                        "report_id": report_id,
                        "corrective_action_id": action["id"],
                        "verification_id": verification["id"],
                        "receipt_id": receipt["id"],
                    },
                    transaction_connection=conn,
                )
                target = ReportStatus.VERIFIED_CLOSED
                transition_reason = None
            else:
                if clean_due_at is None:
                    raise RuntimeError("failed verification lost its validated due date")
                assignment = await conn.fetchrow(
                    """
                    update report_assignments
                    set due_at = $2
                    where id = $1 and active
                    returning *
                    """,
                    action["assignment_id"],
                    clean_due_at,
                )
                if assignment is None:
                    raise VerificationError(
                        "verification_assignment_changed",
                        "active assignment changed during verification",
                    )
                updated_action = await conn.fetchrow(
                    """
                    update corrective_actions
                    set status = 'assigned'::action_status,
                        rework_count = rework_count + 1,
                        due_at = $2
                    where id = $1
                    returning *
                    """,
                    action["id"],
                    clean_due_at,
                )
                if updated_action is None:
                    raise RuntimeError("corrective action disappeared during rework")
                await send_notification(
                    action["assignee_id"],
                    "sent_back",
                    NotificationEntity("report", report_id),
                    {
                        "report_id": report_id,
                        "assignment_id": action["assignment_id"],
                        "corrective_action_id": action["id"],
                        "verification_id": verification["id"],
                        "rework_count": updated_action["rework_count"],
                    },
                    transaction_connection=conn,
                )
                target = ReportStatus.ACTION_ASSIGNED
                transition_reason = clean_reason

            transitioned = await transition_report(
                report_id,
                target,
                actor,
                reason=transition_reason,
                metadata={
                    "verification_id": str(verification["id"]),
                    "corrective_action_id": str(action["id"]),
                    "assignment_id": str(action["assignment_id"]),
                    "rework_count": int(updated_action["rework_count"]),
                    "new_due_at": clean_due_at.isoformat() if clean_due_at else None,
                },
                transaction_connection=conn,
            )
            committed_assignment = await conn.fetchrow(
                "select * from report_assignments where id = $1",
                action["assignment_id"],
            )
            if committed_assignment is None:
                raise RuntimeError("assignment disappeared during verification")
            return VerificationResult(
                verification,
                transitioned,
                updated_action,
                committed_assignment,
            )
