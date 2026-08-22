"""Apply deterministic safety gates before a draft can enter human review."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Final

from app.domain.enums import ValidationStatus

MINIMUM_CONFIDENCE: Final = 0.70

OBSERVED_FACTS_REQUIRED: Final = "observed_facts_required"
ASSUMPTION_IN_OBSERVED_FACTS: Final = "assumption_in_observed_facts"
PROPOSED_URGENCY_REQUIRED: Final = "proposed_urgency_required"
CONFIDENCE_BELOW_THRESHOLD: Final = "confidence_below_threshold"
ESCALATION_REASON_REQUIRED: Final = "escalation_reason_required"
SUGGESTED_ACTION_CITATION_REQUIRED: Final = "suggested_action_citation_required"
CITATION_SOURCE_UNRESOLVED: Final = "citation_source_unresolved"
CITATION_QUOTE_NOT_VERBATIM: Final = "citation_quote_not_verbatim"
SUGGESTED_ACTION_NOT_QUOTED: Final = "suggested_action_not_quoted"

_CJK_RANGE: Final = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_CJK_WHITESPACE = re.compile(rf"(?<=[{_CJK_RANGE}]) (?=[{_CJK_RANGE}])")


def _normalise_claim(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalise_whitespace(value: str) -> str:
    collapsed = " ".join(value.split())
    return _CJK_WHITESPACE.sub("", collapsed)


def _citation_fields(
    citation: object,
) -> tuple[str, str, str, str | None, int | None, str] | None:
    if not isinstance(citation, dict):
        return None
    document_id = citation.get("document_id")
    doc_ref = citation.get("doc_ref")
    revision = citation.get("revision")
    section = citation.get("section")
    page = citation.get("page")
    quote = citation.get("quote")
    if (
        not isinstance(document_id, str)
        or not document_id.strip()
        or not isinstance(doc_ref, str)
        or not doc_ref.strip()
        or not isinstance(revision, str)
        or not revision.strip()
        or section is not None
        and not isinstance(section, str)
        or page is not None
        and (not isinstance(page, int) or isinstance(page, bool))
        or not isinstance(quote, str)
        or not quote.strip()
    ):
        return None
    return document_id, doc_ref, revision, section, page, quote


def _source_matches(
    source: Mapping[str, object],
    fields: tuple[str, str, str, str | None, int | None, str],
) -> bool:
    document_id, doc_ref, revision, section, page, _quote = fields
    return (
        str(source.get("document_id")) == document_id
        and source.get("doc_ref") == doc_ref
        and source.get("revision") == revision
        and source.get("section") == section
        and source.get("page") == page
    )


def _verified_quotes(
    citations: object,
    sources: Sequence[Mapping[str, object]],
) -> tuple[list[str], list[str]]:
    if not isinstance(citations, list):
        return [], []
    verified: list[str] = []
    errors: list[str] = []
    for citation in citations:
        fields = _citation_fields(citation)
        if fields is None:
            errors.append(CITATION_SOURCE_UNRESOLVED)
            continue
        matches = [source for source in sources if _source_matches(source, fields)]
        if not matches:
            errors.append(CITATION_SOURCE_UNRESOLVED)
            continue
        quote = fields[-1]
        normalised_quote = _normalise_whitespace(quote)
        if not any(
            isinstance(source.get("content"), str)
            and normalised_quote
            in _normalise_whitespace(str(source["content"]))
            for source in matches
        ):
            errors.append(CITATION_QUOTE_NOT_VERBATIM)
            continue
        verified.append(quote)
    return verified, errors


def validate_draft(
    draft: Mapping[str, object],
    *,
    citation_sources: Sequence[Mapping[str, object]] = (),
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

    citations = draft.get("citations")
    verified_quotes, citation_errors = _verified_quotes(citations, citation_sources)
    errors.extend(citation_errors)

    suggested_action = draft.get("suggested_action")
    if isinstance(suggested_action, str) and suggested_action.strip():
        if not isinstance(citations, list) or not citations:
            errors.append(SUGGESTED_ACTION_CITATION_REQUIRED)
        elif verified_quotes and not any(
            _normalise_whitespace(suggested_action)
            in _normalise_whitespace(quote)
            for quote in verified_quotes
        ):
            errors.append(SUGGESTED_ACTION_NOT_QUOTED)

    unique_errors = list(dict.fromkeys(errors))
    status = ValidationStatus.INVALID if unique_errors else ValidationStatus.VALID
    return status, unique_errors
