"""Expose the thin HTTP surface for report creation, reads, and transitions."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.deps import current_actor
from app.domain.enums import (
    CaseRole,
    InputMode,
    MediaPhase,
    ReportStatus,
    ReviewDecision,
    Role,
    Urgency,
)
from app.domain.transitions import TransitionError, allowed_targets, find
from app.services.action_service import ActionError, submit_action
from app.services.media_service import (
    MediaError,
    assert_report_readable,
    get_signed_media_urls,
    get_signed_report_media,
    register_report_media,
)
from app.services.intake_service import (
    ClarificationError,
    answer_clarification,
    list_report_clarifications,
    run_intake,
)
from app.services.report_service import (
    Actor,
    ReportDraftError,
    ReportListError,
    create_report,
    get_report,
    get_timeline,
    list_reports,
    transition_report,
    update_draft_report,
)
from app.services.review_service import ReviewError, review_report

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReportRequest(BaseModel):
    """Fields needed to create a draft observation."""

    description_original: str = Field(min_length=1)
    lang_original: str = "en"
    urgency: str = "medium"
    location_text: str | None = None
    activity: str | None = None
    level_or_zone: str | None = None
    grid_ref: str | None = None
    is_confidential: bool = False
    input_mode: InputMode = InputMode.TYPED


class TransitionRequest(BaseModel):
    """Requested state-machine edge and its optional audit context."""

    target: ReportStatus
    reason: str | None = None
    metadata: dict[str, Any] | None = None


class RegisterMediaRequest(BaseModel):
    """Describe an object already uploaded to private Supabase Storage."""

    storage_path: str = Field(min_length=1, max_length=1024)
    mime_type: str = Field(min_length=1, max_length=100)
    phase: MediaPhase
    caption: str | None = Field(default=None, max_length=500)


class ReviewRequest(BaseModel):
    """Capture one reviewer decision and its optional correction diff."""

    decision: ReviewDecision
    target: ReportStatus
    reason: str | None = None
    corrected_category: str | None = Field(default=None, max_length=200)
    corrected_urgency: Urgency | None = None
    corrected_action: str | None = Field(default=None, max_length=4000)
    correction_reason: str | None = Field(default=None, max_length=2000)
    assignee_id: UUID | None = None
    due_at: datetime | None = None


class AssignmentRequest(BaseModel):
    """Approve the current action while naming its responsible owner."""

    assignee_id: UUID | None = None
    case_role: CaseRole
    due_at: datetime | None = None


class ActionSubmitRequest(BaseModel):
    """Reference proof already registered through the private media endpoint."""

    completed_note: str | None = Field(default=None, max_length=4000)
    media_ids: list[UUID] = Field(default_factory=list, max_length=10)


class ClarificationAnswerRequest(BaseModel):
    """Carry reporter-supplied text for one pending clarification."""

    answer: str = Field(max_length=4000)


_REVIEW_DECISION_BY_EVENT = {
    "approve_action": ReviewDecision.APPROVE,
    "approve_after_escalation": ReviewDecision.APPROVE,
    "request_info": ReviewDecision.REQUEST_INFO,
    "escalate": ReviewDecision.ESCALATE,
    "reject": ReviewDecision.REJECT,
    "reject_after_escalation": ReviewDecision.REJECT,
}


def transition_error(error: TransitionError) -> HTTPException:
    """Map machine error codes to the HTTP contract without user-facing prose."""
    code_status = {
        "illegal_transition": status.HTTP_409_CONFLICT,
        "terminal_state": status.HTTP_409_CONFLICT,
        "role_not_permitted": status.HTTP_403_FORBIDDEN,
        "actor_not_permitted": status.HTTP_403_FORBIDDEN,
        "reason_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "assignment_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "unknown_event": status.HTTP_400_BAD_REQUEST,
        "database_guard": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


def review_error(error: ReviewError) -> HTTPException:
    """Map atomic-review failures to localisable machine codes."""
    code_status = {
        "report_not_found": status.HTTP_404_NOT_FOUND,
        "review_actor_not_permitted": status.HTTP_403_FORBIDDEN,
        "review_target_mismatch": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "review_correction_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "correction_reason_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "assignment_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "due_at_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "assignee_not_responsible": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "active_assignment_exists": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


def media_error(error: MediaError) -> HTTPException:
    """Map media failures to stable machine-readable HTTP contracts."""
    code_status = {
        "report_not_found": status.HTTP_404_NOT_FOUND,
        "report_forbidden": status.HTTP_403_FORBIDDEN,
        "media_actor_not_permitted": status.HTTP_403_FORBIDDEN,
        "media_phase_not_permitted": status.HTTP_403_FORBIDDEN,
        "media_path_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_type_not_allowed": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "media_type_mismatch": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        "media_object_not_found": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_object_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "media_already_registered": status.HTTP_409_CONFLICT,
        "storage_not_configured": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "storage_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "storage_sign_failed": status.HTTP_502_BAD_GATEWAY,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


def action_error(error: ActionError) -> HTTPException:
    """Map corrective-action failures to localisable machine contracts."""
    code_status = {
        "action_actor_forbidden": status.HTTP_403_FORBIDDEN,
        "action_forbidden": status.HTTP_403_FORBIDDEN,
        "action_not_found": status.HTTP_404_NOT_FOUND,
        "action_not_submittable": status.HTTP_409_CONFLICT,
        "action_evidence_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "action_media_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


def report_list_error(error: ReportListError) -> HTTPException:
    """Map list-query failures to stable API error contracts."""
    code_status = {
        "report_list_forbidden": status.HTTP_403_FORBIDDEN,
        "invalid_cursor": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_page_size": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_assignee": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "assignee_me_forbidden": status.HTTP_403_FORBIDDEN,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


def _resolve_assignee_filter(
    assignee: str | UUID | None,
    actor: Actor,
) -> UUID | None:
    if assignee is None or isinstance(assignee, UUID):
        return assignee
    if assignee == "me":
        if actor.role is not Role.RESPONSIBLE or actor.profile_id is None:
            raise ReportListError(
                "assignee_me_forbidden",
                "assignee me filter requires a responsible profile",
            )
        return actor.profile_id
    try:
        return UUID(assignee)
    except ValueError as error:
        raise ReportListError(
            "invalid_assignee",
            "assignee filter must be a profile id or me",
        ) from error


def report_draft_error(error: ReportDraftError) -> HTTPException:
    """Map reporter-owned draft finalisation failures to stable codes."""
    code_status = {
        "report_not_found": status.HTTP_404_NOT_FOUND,
        "report_forbidden": status.HTTP_403_FORBIDDEN,
        "draft_update_forbidden": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


def clarification_error(error: ClarificationError) -> HTTPException:
    """Map clarification failures to localisable machine codes."""
    code_status = {
        "report_not_found": status.HTTP_404_NOT_FOUND,
        "clarification_not_found": status.HTTP_404_NOT_FOUND,
        "clarification_actor_forbidden": status.HTTP_403_FORBIDDEN,
        "clarification_forbidden": status.HTTP_403_FORBIDDEN,
        "clarification_answer_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "report_not_clarifying": status.HTTP_409_CONFLICT,
        "clarification_already_answered": status.HTTP_409_CONFLICT,
        "clarification_round_invalid": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        {"code": error.code, "message": error.message},
    )


@router.get("")
async def report_list(
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    urgency: Urgency | None = Query(default=None),
    assignee_id: str | UUID | None = Query(default=None, alias="assignee"),
    needs_manual_triage: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=25, ge=1, le=100),
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Return one role-scoped queue page and its opaque continuation cursor."""
    try:
        resolved_assignee_id = _resolve_assignee_filter(assignee_id, actor)
        page = await list_reports(
            actor,
            report_status=report_status,
            urgency=urgency,
            assignee_id=resolved_assignee_id,
            needs_manual_triage=needs_manual_triage,
            query=q,
            cursor=cursor,
            limit=limit,
        )
        raw_items = [dict(row) for row in page.rows]
        paths: list[str] = []
        for item in raw_items:
            thumbnail_path = item.get("thumbnail_storage_path")
            if isinstance(thumbnail_path, str):
                paths.append(thumbnail_path)
            previous_evidence = item.get("previous_evidence", [])
            if isinstance(previous_evidence, str):
                previous_evidence = json.loads(previous_evidence)
            if not isinstance(previous_evidence, list):
                previous_evidence = []
            normalized_evidence = [
                dict(evidence)
                for evidence in previous_evidence
                if isinstance(evidence, dict)
            ]
            item["previous_evidence"] = normalized_evidence
            paths.extend(
                evidence_path
                for evidence in normalized_evidence
                if isinstance(
                    evidence_path := evidence.get("storage_path"),
                    str,
                )
            )
        signed_urls, expires_at = await get_signed_media_urls(paths)
    except ReportListError as error:
        raise report_list_error(error) from error
    except MediaError as error:
        raise media_error(error) from error

    items: list[dict[str, object]] = []
    for item in raw_items:
        item.pop("_urgency_rank", None)
        storage_path = item.pop("thumbnail_storage_path", None)
        item["thumbnail_url"] = signed_urls.get(storage_path) if isinstance(storage_path, str) else None
        item["thumbnail_url_expires_at"] = expires_at if isinstance(storage_path, str) else None
        previous_evidence = item.get("previous_evidence", [])
        if isinstance(previous_evidence, list):
            for evidence in previous_evidence:
                if not isinstance(evidence, dict):
                    continue
                evidence_path = evidence.pop("storage_path", None)
                evidence["signed_url"] = (
                    signed_urls.get(evidence_path)
                    if isinstance(evidence_path, str)
                    else None
                )
                evidence["signed_url_expires_at"] = (
                    expires_at if isinstance(evidence_path, str) else None
                )
        items.append(item)
    return cast(
        dict[str, object],
        jsonable_encoder({"items": items, "next_cursor": page.next_cursor}),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_report(payload: CreateReportRequest, actor: Actor = Depends(current_actor)) -> dict[str, UUID]:
    """Create a draft owned by the authenticated debug actor."""
    if actor.profile_id is None:
        raise HTTPException(403, {"code": "profile_required", "message": "human profile is required"})
    report_id = await create_report(
        actor.profile_id,
        payload.description_original,
        lang_original=payload.lang_original,
        urgency=payload.urgency,
        location_text=payload.location_text,
        activity=payload.activity,
        level_or_zone=payload.level_or_zone,
        grid_ref=payload.grid_ref,
        is_confidential=payload.is_confidential,
        input_mode=payload.input_mode,
    )
    return {"id": report_id}


@router.patch("/{report_id}")
async def patch_report_draft(
    report_id: UUID,
    payload: CreateReportRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Update only the caller's draft before the normal submit transition."""
    if actor.profile_id is None:
        raise HTTPException(403, {"code": "profile_required", "message": "human profile is required"})
    try:
        report = await update_draft_report(
            report_id,
            actor.profile_id,
            payload.description_original,
            lang_original=payload.lang_original,
            location_text=payload.location_text,
            activity=payload.activity,
            level_or_zone=payload.level_or_zone,
            grid_ref=payload.grid_ref,
            is_confidential=payload.is_confidential,
            input_mode=payload.input_mode,
        )
    except ReportDraftError as error:
        raise report_draft_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(report)))


@router.get("/{report_id}")
async def report_detail(report_id: UUID, actor: Actor = Depends(current_actor)) -> dict[str, object]:
    """Return a report and the legal targets for the calling actor."""
    report = await get_report(report_id)
    if report is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    try:
        assert_report_readable(report, actor)
        media = await get_signed_report_media(report_id)
        clarifications = await list_report_clarifications(report_id)
    except MediaError as error:
        raise media_error(error) from error
    source = ReportStatus(report["status"])
    result = dict(report)
    latest_draft = result.get("latest_draft")
    if isinstance(latest_draft, str):
        result["latest_draft"] = json.loads(latest_draft)
    elif latest_draft is None:
        result["latest_draft"] = None
    result["media"] = media
    result["clarifications"] = [dict(row) for row in clarifications]
    available: list[dict[str, object]] = []
    for target in allowed_targets(source, actor.actor_type, actor.role):
        transition = find(source, target)
        if transition is None:
            raise RuntimeError("allowed state-machine target has no transition")
        transition_payload: dict[str, object] = {
            "event": transition.event,
            "target": transition.target.value,
            "requires_reason": transition.requires_reason,
        }
        decision = _REVIEW_DECISION_BY_EVENT.get(transition.event)
        if decision is not None:
            transition_payload["review_decision"] = decision.value
        available.append(transition_payload)
    result["available_transitions"] = available
    return cast(dict[str, object], jsonable_encoder(result))


@router.post("/{report_id}/media", status_code=status.HTTP_201_CREATED)
async def post_report_media(
    report_id: UUID,
    payload: RegisterMediaRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Register one private object only after checking its stored metadata."""
    try:
        media = await register_report_media(
            report_id,
            actor,
            storage_path=payload.storage_path,
            mime_type=payload.mime_type,
            phase=payload.phase,
            caption=payload.caption,
        )
    except MediaError as error:
        raise media_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(media)))


@router.post("/{report_id}/assignments", status_code=status.HTTP_201_CREATED)
async def post_assignment(
    report_id: UUID,
    payload: AssignmentRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Approve and assign through the existing all-or-nothing review transaction."""
    try:
        result = await review_report(
            report_id,
            actor,
            decision=ReviewDecision.APPROVE,
            target=ReportStatus.ACTION_ASSIGNED,
            assignee_id=payload.assignee_id,
            case_role=payload.case_role,
            due_at=payload.due_at,
        )
    except ReviewError as error:
        raise review_error(error) from error
    except TransitionError as error:
        raise transition_error(error) from error
    return cast(
        dict[str, object],
        jsonable_encoder(
            {
                "review_id": result.review["id"],
                "report_id": result.report["id"],
                "status": result.report["status"],
                "assignment_id": result.assignment_id,
                "corrective_action_id": result.corrective_action_id,
            }
        ),
    )


@router.post("/{report_id}/actions/{action_id}/submit")
async def post_action_submission(
    report_id: UUID,
    action_id: UUID,
    payload: ActionSubmitRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Commit technician proof and the submit-evidence transition together."""
    try:
        result = await submit_action(
            report_id,
            action_id,
            actor,
            completed_note=payload.completed_note,
            media_ids=payload.media_ids,
        )
    except ActionError as error:
        raise action_error(error) from error
    except TransitionError as error:
        raise transition_error(error) from error
    return cast(
        dict[str, object],
        jsonable_encoder(
            {
                "report_id": result.report["id"],
                "action_id": result.action["id"],
                "status": result.report["status"],
                "completed_note": result.action["completed_note"],
                "submitted_at": result.action["submitted_at"],
                "media_ids": result.media_ids,
            }
        ),
    )


@router.post("/{report_id}/review")
async def post_review(
    report_id: UUID,
    payload: ReviewRequest,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Commit the review row and its transition through the sole status writer."""
    try:
        result = await review_report(
            report_id,
            actor,
            decision=payload.decision,
            target=payload.target,
            reason=payload.reason,
            corrected_category=payload.corrected_category,
            corrected_urgency=payload.corrected_urgency,
            corrected_action=payload.corrected_action,
            correction_reason=payload.correction_reason,
            assignee_id=payload.assignee_id,
            due_at=payload.due_at,
        )
    except ReviewError as error:
        raise review_error(error) from error
    except TransitionError as error:
        raise transition_error(error) from error
    return cast(
        dict[str, object],
        jsonable_encoder(
            {
                "review_id": result.review["id"],
                "report_id": result.report["id"],
                "status": result.report["status"],
                "assignment_id": result.assignment_id,
                "corrective_action_id": result.corrective_action_id,
            }
        ),
    )


@router.get("/{report_id}/timeline")
async def report_timeline(report_id: UUID, actor: Actor = Depends(current_actor)) -> list[dict[str, object]]:
    """Return the report's audit timeline."""
    report = await get_report(report_id)
    if report is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    try:
        assert_report_readable(report, actor)
    except MediaError as error:
        raise media_error(error) from error
    return cast(
        list[dict[str, object]],
        jsonable_encoder([dict(row) for row in await get_timeline(report_id)]),
    )


@router.post("/{report_id}/transition")
async def post_transition(
    report_id: UUID,
    payload: TransitionRequest,
    background_tasks: BackgroundTasks,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Apply one legal transition through the sole status-writing service."""
    existing_report = await get_report(report_id)
    if existing_report is None:
        raise HTTPException(404, {"code": "report_not_found", "message": "report does not exist"})
    try:
        assert_report_readable(existing_report, actor)
        report = await transition_report(
            report_id,
            payload.target,
            actor,
            reason=payload.reason,
            metadata=payload.metadata,
        )
    except MediaError as error:
        raise media_error(error) from error
    except TransitionError as error:
        raise transition_error(error) from error
    if payload.target is ReportStatus.SUBMITTED:
        background_tasks.add_task(run_intake, report_id)
    return cast(dict[str, object], jsonable_encoder(dict(report)))


@router.post("/{report_id}/clarifications/{clarification_id}/answer")
async def post_clarification_answer(
    report_id: UUID,
    clarification_id: UUID,
    payload: ClarificationAnswerRequest,
    background_tasks: BackgroundTasks,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Store one answer and resume intake after the active round is complete."""
    try:
        result = await answer_clarification(
            report_id,
            clarification_id,
            actor,
            payload.answer,
        )
    except ClarificationError as error:
        raise clarification_error(error) from error
    if result.rerun:
        background_tasks.add_task(run_intake, report_id)
    return cast(
        dict[str, object],
        jsonable_encoder(
            {
                "id": result.clarification["id"],
                "report_id": result.clarification["report_id"],
                "answered_at": result.clarification["answered_at"],
                "round_complete": result.rerun,
            }
        ),
    )
