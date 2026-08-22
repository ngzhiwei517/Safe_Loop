"""Apply deterministic safety gates before a draft can enter human review."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from app.domain.enums import ValidationStatus

MINIMUM_CONFIDENCE: Final = 0.70

OBSERVED_FACTS_REQUIRED: Final = "observed_facts_required"
ASSUMPTION_IN_OBSERVED_FACTS: Final = "assumption_in_observed_facts"
PROPOSED_URGENCY_REQUIRED: Final = "proposed_urgency_required"
CONFIDENCE_BELOW_THRESHOLD: Final = "confidence_below_threshold"
ESCALATION_REASON_REQUIRED: Final = "escalation_reason_required"
SUGGESTED_ACTION_CITATION_REQUIRED: Final = "suggested_action_citation_required"

_CITATION_FIELDS: Final = (
    "document_id",
    "doc_ref",
    "revision",
    "section",
    "page",
    "quote",
)


def _normalise_claim(value: str) -> str:
    return " ".join(value.casefold().split())


def _has_structured_citation(citations: object) -> bool:
    """Require all evidence coordinates now; Phase 3 verifies the quoted source."""
    if not isinstance(citations, list):
        return False
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        if all(
            field in citation
            and citation[field] is not None
            and str(citation[field]).strip()
            for field in _CITATION_FIELDS
        ):
            return True
    return False


def validate_draft(
    draft: Mapping[str, object],
    *,
    confidence_threshold: float = MINIMUM_CONFIDENCE,
) -> tuple[ValidationStatus, list[str]]:
    """Return stable error codes without mutating or enriching model output."""
    errors: list[str] = []
    observed = draft.get("observed_facts")
    assumptions = draft.get("assumptions")

    observed_claims = (
        [claim for claim in observed if isinstance(claim, str) and claim.strip()]
        if isinstance(observed, list)
        else []
    )
    assumption_claims = (
        [claim for claim in assumptions if isinstance(claim, str) and claim.strip()]
        if isinstance(assumptions, list)
        else []
    )
    if not observed_claims:
        errors.append(OBSERVED_FACTS_REQUIRED)

    normalised_assumptions = {_normalise_claim(claim) for claim in assumption_claims}
    if any(
        _normalise_claim(claim) in normalised_assumptions for claim in observed_claims
    ):
        errors.append(ASSUMPTION_IN_OBSERVED_FACTS)

    urgency = draft.get("proposed_urgency")
    if not isinstance(urgency, str) or not urgency.strip():
        errors.append(PROPOSED_URGENCY_REQUIRED)

    confidence = draft.get("confidence")
    if (
        not isinstance(confidence, int | float)
        or isinstance(confidence, bool)
        or float(confidence) < confidence_threshold
    ):
        errors.append(CONFIDENCE_BELOW_THRESHOLD)

    if draft.get("needs_escalation") is True:
        escalation_reason = draft.get("escalation_reason")
        if not isinstance(escalation_reason, str) or not escalation_reason.strip():
            errors.append(ESCALATION_REASON_REQUIRED)

    suggested_action = draft.get("suggested_action")
    if (
        isinstance(suggested_action, str)
        and suggested_action.strip()
        and not _has_structured_citation(draft.get("citations"))
    ):
        errors.append(SUGGESTED_ACTION_CITATION_REQUIRED)

    status = ValidationStatus.INVALID if errors else ValidationStatus.VALID
    return status, errors
