"""Exercise every deterministic reason a draft can fail the safety gate."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.ai.intake_graph import DraftPayload
from app.ai.validator import (
    ASSUMPTION_IN_OBSERVED_FACTS,
    CITATION_QUOTE_NOT_VERBATIM,
    CONFIDENCE_BELOW_THRESHOLD,
    ESCALATION_REASON_REQUIRED,
    OBSERVED_FACTS_REQUIRED,
    PROPOSED_URGENCY_REQUIRED,
    SUGGESTED_ACTION_CITATION_REQUIRED,
    SUGGESTED_ACTION_NOT_QUOTED,
    validate_draft,
)
from app.domain.enums import ValidationStatus


def valid_draft() -> DraftPayload:
    return {
        "observed_facts": ["A guardrail is missing at Level 6."],
        "assumptions": ["The guardrail may have been removed."],
        "missing_information": [],
        "proposed_category": "work_at_height",
        "proposed_urgency": "high",
        "suggested_owner_role": "responsible",
        "suggested_action": None,
        "confidence": 0.9,
        "needs_escalation": False,
        "escalation_reason": None,
        "citations": [],
    }


def test_good_draft_passes_without_errors() -> None:
    assert validate_draft(valid_draft()) == (ValidationStatus.VALID, [])


@pytest.mark.parametrize(
    ("changes", "expected_error"),
    [
        ({"observed_facts": []}, OBSERVED_FACTS_REQUIRED),
        (
            {
                "observed_facts": [" The worker was careless "],
                "assumptions": ["the worker was careless"],
            },
            ASSUMPTION_IN_OBSERVED_FACTS,
        ),
        ({"proposed_urgency": None}, PROPOSED_URGENCY_REQUIRED),
        ({"confidence": 0.69}, CONFIDENCE_BELOW_THRESHOLD),
        (
            {"needs_escalation": True, "escalation_reason": "  "},
            ESCALATION_REASON_REQUIRED,
        ),
        (
            {"suggested_action": "Install a temporary guardrail.", "citations": []},
            SUGGESTED_ACTION_CITATION_REQUIRED,
        ),
    ],
)
def test_each_gate_returns_a_machine_code(
    changes: dict[str, object],
    expected_error: str,
) -> None:
    draft = deepcopy(valid_draft())
    draft.update(changes)  # type: ignore[typeddict-item]

    validation, errors = validate_draft(draft)

    assert validation is ValidationStatus.INVALID
    assert expected_error in errors


def citation_source(content: str) -> dict[str, object]:
    return {
        "document_id": "10000000-0000-0000-0000-000000000001",
        "doc_ref": "WAH-001",
        "revision": "3",
        "section": "4.2",
        "page": 7,
        "content": content,
    }


def test_verified_citation_allows_a_verbatim_action() -> None:
    draft = valid_draft()
    draft["suggested_action"] = "Install edge protection before work starts."
    draft["citations"] = [
        {
            "document_id": "10000000-0000-0000-0000-000000000001",
            "doc_ref": "WAH-001",
            "revision": "3",
            "section": "4.2",
            "page": 7,
            "quote": "Install edge protection before work starts.",
        }
    ]

    assert validate_draft(
        draft,
        citation_sources=[
            citation_source("Install edge protection before work starts.")
        ],
    ) == (ValidationStatus.VALID, [])


def test_fabricated_quote_is_rejected_with_a_specific_code() -> None:
    draft = valid_draft()
    draft["suggested_action"] = "Install a temporary guardrail."
    draft["citations"] = [
        {
            "document_id": "10000000-0000-0000-0000-000000000001",
            "doc_ref": "WAH-001",
            "revision": "3",
            "section": "4.2",
            "page": 7,
            "quote": "Install a temporary guardrail.",
        }
    ]

    validation, errors = validate_draft(
        draft,
        citation_sources=[citation_source("Inspect the edge before work starts.")],
    )

    assert validation is ValidationStatus.INVALID
    assert CITATION_QUOTE_NOT_VERBATIM in errors


def test_cjk_quote_matches_when_only_whitespace_differs() -> None:
    draft = valid_draft()
    draft["suggested_action"] = "必须安装防护栏。"
    draft["citations"] = [
        {
            "document_id": "10000000-0000-0000-0000-000000000001",
            "doc_ref": "WAH-001",
            "revision": "3",
            "section": "4.2",
            "page": 7,
            "quote": "必须\n安装防护栏。",
        }
    ]

    assert validate_draft(
        draft,
        citation_sources=[citation_source("开始工作前必须安装防护栏。")],
    ) == (ValidationStatus.VALID, [])


def test_action_must_itself_appear_in_a_verified_quote() -> None:
    draft = valid_draft()
    draft["suggested_action"] = "Stop all work."
    draft["citations"] = [
        {
            "document_id": "10000000-0000-0000-0000-000000000001",
            "doc_ref": "WAH-001",
            "revision": "3",
            "section": "4.2",
            "page": 7,
            "quote": "Install edge protection before work starts.",
        }
    ]

    validation, errors = validate_draft(
        draft,
        citation_sources=[
            citation_source("Install edge protection before work starts.")
        ],
    )

    assert validation is ValidationStatus.INVALID
    assert SUGGESTED_ACTION_NOT_QUOTED in errors
