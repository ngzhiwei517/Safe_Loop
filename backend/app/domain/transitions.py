"""Implement the pure, auditable report state machine."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import ActorType, ReportStatus, Role


class TransitionError(Exception):
    """Represent a machine-readable refusal to perform a transition."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Transition:
    """Describe one legal edge in the report state machine."""

    event: str
    source: ReportStatus
    target: ReportStatus
    actor_types: frozenset[ActorType]
    roles: frozenset[Role]
    requires_reason: bool
    note: str


def _transition(
    event: str,
    source: ReportStatus,
    target: ReportStatus,
    actor_types: frozenset[ActorType],
    roles: frozenset[Role],
    requires_reason: bool = False,
    note: str = "",
) -> Transition:
    return Transition(event, source, target, actor_types, roles, requires_reason, note)


TRANSITIONS = (
    _transition("submit", ReportStatus.DRAFT, ReportStatus.SUBMITTED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REPORTER})),
    _transition("start_clarification", ReportStatus.SUBMITTED, ReportStatus.CLARIFYING,
                frozenset({ActorType.AI, ActorType.SYSTEM}), frozenset()),
    _transition("draft_without_clarification", ReportStatus.SUBMITTED, ReportStatus.AI_DRAFTED,
                frozenset({ActorType.AI, ActorType.SYSTEM}), frozenset()),
    _transition("clarification_complete", ReportStatus.CLARIFYING, ReportStatus.AI_DRAFTED,
                frozenset({ActorType.AI, ActorType.SYSTEM}), frozenset()),
    _transition("queue_for_review", ReportStatus.AI_DRAFTED, ReportStatus.UNDER_REVIEW,
                frozenset({ActorType.SYSTEM}), frozenset()),
    _transition("reject", ReportStatus.UNDER_REVIEW, ReportStatus.REJECTED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER}), True),
    _transition("request_info", ReportStatus.UNDER_REVIEW, ReportStatus.INFO_REQUESTED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER}), True),
    _transition("provide_info", ReportStatus.INFO_REQUESTED, ReportStatus.CLARIFYING,
                frozenset({ActorType.HUMAN}), frozenset({Role.REPORTER})),
    _transition("escalate", ReportStatus.UNDER_REVIEW, ReportStatus.ESCALATED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER}), True),
    _transition("approve_action", ReportStatus.UNDER_REVIEW, ReportStatus.ACTION_ASSIGNED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER})),
    _transition("approve_after_escalation", ReportStatus.ESCALATED, ReportStatus.ACTION_ASSIGNED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER})),
    _transition("reject_after_escalation", ReportStatus.ESCALATED, ReportStatus.REJECTED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER}), True),
    _transition("submit_evidence", ReportStatus.ACTION_ASSIGNED, ReportStatus.ACTION_SUBMITTED,
                frozenset({ActorType.HUMAN}), frozenset({Role.RESPONSIBLE})),
    _transition("verification_failed", ReportStatus.ACTION_SUBMITTED, ReportStatus.ACTION_ASSIGNED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER}), True),
    _transition("verify_and_close", ReportStatus.ACTION_SUBMITTED, ReportStatus.VERIFIED_CLOSED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER})),
    _transition("draft_lesson", ReportStatus.VERIFIED_CLOSED, ReportStatus.LESSON_DRAFTED,
                frozenset({ActorType.AI, ActorType.SYSTEM}), frozenset()),
    _transition("publish_lesson", ReportStatus.LESSON_DRAFTED, ReportStatus.LESSON_PUBLISHED,
                frozenset({ActorType.HUMAN}), frozenset({Role.REVIEWER})),
)


def _assert_unique_transitions() -> None:
    edges = [(transition.source, transition.target) for transition in TRANSITIONS]
    events = [transition.event for transition in TRANSITIONS]
    if len(edges) != len(set(edges)):
        raise RuntimeError("duplicate transition edge")
    if len(events) != len(set(events)):
        raise RuntimeError("duplicate transition event")


_assert_unique_transitions()


def find(source: ReportStatus, target: ReportStatus) -> Transition | None:
    """Return the edge between two statuses, if one exists."""
    return next(
        (transition for transition in TRANSITIONS
         if transition.source == source and transition.target == target),
        None,
    )


def by_event(event: str) -> Transition | None:
    """Return the edge named by an event, if one exists."""
    return next((transition for transition in TRANSITIONS if transition.event == event), None)


def allowed_targets(
    source: ReportStatus,
    actor_type: ActorType,
    role: Role | None = None,
) -> tuple[ReportStatus, ...]:
    """Return targets legal for the supplied actor at a source status."""
    return tuple(
        transition.target
        for transition in TRANSITIONS
        if transition.source == source
        and actor_type in transition.actor_types
        and (not transition.roles or role in transition.roles)
    )


def assert_can(
    source: ReportStatus,
    target: ReportStatus,
    actor_type: ActorType,
    role: Role | None = None,
    reason: str | None = None,
) -> Transition:
    """Validate one requested edge and return its transition definition."""
    if source in {ReportStatus.REJECTED, ReportStatus.LESSON_PUBLISHED}:
        raise TransitionError("terminal_state", "terminal status has no outgoing transitions")

    transition = find(source, target)
    if transition is None:
        raise TransitionError("illegal_transition", "status edge is not defined")
    if actor_type not in transition.actor_types:
        raise TransitionError("actor_not_permitted", "actor type cannot perform this transition")
    if transition.roles and role not in transition.roles:
        raise TransitionError("role_not_permitted", "role cannot perform this transition")
    if transition.requires_reason and not reason.strip() if reason is not None else transition.requires_reason:
        raise TransitionError("reason_required", "transition requires a non-empty reason")
    return transition
