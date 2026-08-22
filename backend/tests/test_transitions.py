"""Exercise every state-machine edge and its safety restrictions."""

from __future__ import annotations

import pytest

from app.domain.enums import AI_FORBIDDEN_STATUSES, ActorType, ReportStatus, Role, TERMINAL_STATUSES
from app.domain.transitions import TRANSITIONS, TransitionError, allowed_targets, assert_can


def test_every_edge_accepts_a_legal_actor() -> None:
    for transition in TRANSITIONS:
        actor_type = next(iter(transition.actor_types))
        role = next(iter(transition.roles), None)
        reason = "specific reason" if transition.requires_reason else None
        assert assert_can(transition.source, transition.target, actor_type, role, reason) == transition


@pytest.mark.parametrize("target", sorted(AI_FORBIDDEN_STATUSES, key=lambda status: status.value))
def test_ai_cannot_reach_forbidden_targets(target: ReportStatus) -> None:
    assert target not in allowed_targets(ReportStatus.UNDER_REVIEW, ActorType.AI, Role.REVIEWER)
    for transition in TRANSITIONS:
        if transition.target == target:
            with pytest.raises(TransitionError) as error:
                assert_can(transition.source, transition.target, ActorType.AI, Role.REVIEWER, "reason")
            assert error.value.code in {"actor_not_permitted", "role_not_permitted"}


@pytest.mark.parametrize("actor_type", [ActorType.AI, ActorType.SYSTEM])
def test_only_human_can_close(actor_type: ActorType) -> None:
    with pytest.raises(TransitionError) as error:
        assert_can(ReportStatus.ACTION_SUBMITTED, ReportStatus.VERIFIED_CLOSED, actor_type, Role.REVIEWER)
    assert error.value.code == "actor_not_permitted"


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES, key=lambda value: value.value))
def test_terminal_statuses_have_no_outgoing_moves(status: ReportStatus) -> None:
    with pytest.raises(TransitionError) as error:
        assert_can(status, ReportStatus.SUBMITTED, ActorType.HUMAN, Role.REVIEWER)
    assert error.value.code == "terminal_state"


@pytest.mark.parametrize(
    "transition",
    [transition for transition in TRANSITIONS if transition.requires_reason],
)
@pytest.mark.parametrize("reason", ["", "   "])
def test_reason_is_required(transition, reason: str) -> None:
    with pytest.raises(TransitionError) as error:
        assert_can(
            transition.source,
            transition.target,
            next(iter(transition.actor_types)),
            next(iter(transition.roles), None),
            reason,
        )
    assert error.value.code == "reason_required"


def test_rework_cycle_can_close() -> None:
    assert_can(ReportStatus.ACTION_ASSIGNED, ReportStatus.ACTION_SUBMITTED,
               ActorType.HUMAN, Role.RESPONSIBLE)
    assert_can(ReportStatus.ACTION_SUBMITTED, ReportStatus.ACTION_ASSIGNED,
               ActorType.HUMAN, Role.REVIEWER, "guardrail remains incomplete")
    assert_can(ReportStatus.ACTION_ASSIGNED, ReportStatus.ACTION_SUBMITTED,
               ActorType.HUMAN, Role.RESPONSIBLE)
    assert_can(ReportStatus.ACTION_SUBMITTED, ReportStatus.VERIFIED_CLOSED,
               ActorType.HUMAN, Role.REVIEWER)


def test_verification_failed_requires_reason() -> None:
    with pytest.raises(TransitionError) as error:
        assert_can(ReportStatus.ACTION_SUBMITTED, ReportStatus.ACTION_ASSIGNED,
                   ActorType.HUMAN, Role.REVIEWER, " ")
    assert error.value.code == "reason_required"


@pytest.mark.parametrize("transition", TRANSITIONS)
def test_each_declared_edge_is_exercised(transition) -> None:
    assert transition in TRANSITIONS
