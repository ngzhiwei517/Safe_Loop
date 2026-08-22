"""Define the dependency-free vocabulary shared by the SafeLoop state machine."""

from __future__ import annotations

from enum import StrEnum


class ReportStatus(StrEnum):
    """Statuses in the report workflow."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    CLARIFYING = "clarifying"
    AI_DRAFTED = "ai_drafted"
    UNDER_REVIEW = "under_review"
    REJECTED = "rejected"
    INFO_REQUESTED = "info_requested"
    ESCALATED = "escalated"
    ACTION_ASSIGNED = "action_assigned"
    ACTION_SUBMITTED = "action_submitted"
    VERIFIED_CLOSED = "verified_closed"
    LESSON_DRAFTED = "lesson_drafted"
    LESSON_PUBLISHED = "lesson_published"


class Role(StrEnum):
    """Application roles that may participate in workflow transitions."""

    REPORTER = "reporter"
    REVIEWER = "reviewer"
    RESPONSIBLE = "responsible"
    CREW = "crew"
    ADMIN = "admin"


class ActorType(StrEnum):
    """Kinds of actors that can cause a state transition."""

    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"


class Urgency(StrEnum):
    """Urgency levels used to order review work."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewDecision(StrEnum):
    """Reviewer decisions recorded against an AI draft."""

    APPROVE = "approve"
    REQUEST_INFO = "request_info"
    ESCALATE = "escalate"
    REJECT = "reject"


class ActionStatus(StrEnum):
    """Lifecycle of a corrective action."""

    ASSIGNED = "assigned"
    SUBMITTED = "submitted"
    VERIFIED = "verified"


class CaseRole(StrEnum):
    """Roles attached to a case assignment."""

    RESPONSIBLE = "responsible"


class MediaPhase(StrEnum):
    """Whether media documents the report or corrective-action evidence."""

    ORIGINAL = "original"
    EVIDENCE = "evidence"


class InputMode(StrEnum):
    """Input path used to create the original report text."""

    TYPED = "typed"
    VOICE = "voice"
    VOICE_EDITED = "voice_edited"


class ValidationStatus(StrEnum):
    """Result of the deterministic safety gate applied to an AI draft."""

    VALID = "valid"
    INVALID = "invalid"


AI_FORBIDDEN_STATUSES = frozenset(
    {
        ReportStatus.UNDER_REVIEW,
        ReportStatus.INFO_REQUESTED,
        ReportStatus.REJECTED,
        ReportStatus.ESCALATED,
        ReportStatus.ACTION_ASSIGNED,
        ReportStatus.ACTION_SUBMITTED,
        ReportStatus.VERIFIED_CLOSED,
        ReportStatus.LESSON_PUBLISHED,
    }
)

TERMINAL_STATUSES = frozenset(
    {ReportStatus.REJECTED, ReportStatus.LESSON_PUBLISHED}
)

SUPPORTED_LOCALES = ("en", "zh-CN")
DEFAULT_LOCALE = "en"
