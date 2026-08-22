"""Evaluate factual grounding, severity tolerance, and citation resolution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import BaseModel, Field

from app.ai.intake_graph import DraftEnvelope, IntakeState, RetrievedProcedure, intake_graph
from app.ai.validator import (
    CITATION_QUOTE_NOT_VERBATIM,
    CITATION_SOURCE_UNRESOLVED,
    SUGGESTED_ACTION_CITATION_REQUIRED,
    SUGGESTED_ACTION_NOT_QUOTED,
    validate_draft,
)
from app.domain.enums import Urgency

MINIMUM_PASS_RATE: Final = 0.80
_FIXTURES_PATH = Path(__file__).with_name("fixtures.json")
_URGENCY_RANK: Final = {
    Urgency.LOW.value: 0,
    Urgency.MEDIUM.value: 1,
    Urgency.HIGH.value: 2,
    Urgency.CRITICAL.value: 3,
}
_CITATION_ERRORS: Final = {
    CITATION_QUOTE_NOT_VERBATIM,
    CITATION_SOURCE_UNRESOLVED,
    SUGGESTED_ACTION_CITATION_REQUIRED,
    SUGGESTED_ACTION_NOT_QUOTED,
}


class EvalSource(BaseModel):
    content: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    doc_ref: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    section: str | None
    page: int | None
    similarity: float = Field(ge=0.35, le=1.0)


class EvalFixture(BaseModel):
    id: str = Field(min_length=1)
    lang_original: Literal["en", "zh-CN"]
    description_original: str = Field(min_length=1)
    location: str | None
    activity: str | None
    expected_urgency: Urgency
    expected_fact_markers: list[str] = Field(min_length=1)
    forbidden_fact_markers: list[str]
    source: EvalSource


@dataclass(frozen=True)
class EvalCaseResult:
    fixture_id: str
    passed: bool
    facts_grounded: bool
    urgency_in_range: bool
    citations_resolvable: bool
    provider: str
    failure: str | None = None


@dataclass(frozen=True)
class EvalReport:
    cases: tuple[EvalCaseResult, ...]

    @property
    def passed(self) -> int:
        return sum(case.passed for case in self.cases)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load_fixtures() -> tuple[EvalFixture, ...]:
    raw = json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("evaluation fixtures must be a list")
    fixtures = tuple(EvalFixture.model_validate(item) for item in raw)
    if len(fixtures) != 15:
        raise ValueError("the intake evaluation must contain exactly 15 fixtures")
    if len({fixture.id for fixture in fixtures}) != len(fixtures):
        raise ValueError("evaluation fixture IDs must be unique")
    code_switched = sum(
        fixture.lang_original == "zh-CN"
        and any(
            marker in fixture.description_original.casefold()
            for marker in ("guardrail", "formwork", "electrical", "cable")
        )
        for fixture in fixtures
    )
    if code_switched < 2:
        raise ValueError("at least two fixtures must mix Mandarin and English trade terms")
    return fixtures


def _state(fixture: EvalFixture) -> IntakeState:
    source = cast(
        RetrievedProcedure,
        fixture.source.model_dump(mode="python"),
    )
    return {
        "report_id": fixture.id,
        "lang_original": fixture.lang_original,
        "preferred_lang": fixture.lang_original,
        "description_original": fixture.description_original,
        "description_en": None,
        "location": fixture.location,
        "activity": fixture.activity,
        "prior_answers": [],
        "round": 2,
        "observed_facts": [],
        "assumptions": [],
        "missing_information": [],
        "questions": [],
        "retrieved_chunks": [source],
        "draft": None,
    }


def _facts_grounded(fixture: EvalFixture, draft: DraftEnvelope) -> bool:
    observed = [fact.casefold() for fact in draft["observed_facts"] if fact.strip()]
    assumptions = {
        " ".join(assumption.casefold().split())
        for assumption in draft["assumptions"]
        if assumption.strip()
    }
    if not observed:
        return False
    if any(" ".join(fact.split()) in assumptions for fact in observed):
        return False
    if not any(
        marker.casefold() in fact
        for marker in fixture.expected_fact_markers
        for fact in observed
    ):
        return False
    return not any(
        marker.casefold() in fact
        for marker in fixture.forbidden_fact_markers
        for fact in observed
    )


def _urgency_in_range(fixture: EvalFixture, draft: DraftEnvelope) -> bool:
    proposed = draft["proposed_urgency"]
    if proposed not in _URGENCY_RANK:
        return False
    return abs(
        _URGENCY_RANK[proposed] - _URGENCY_RANK[fixture.expected_urgency.value]
    ) <= 1


def _citations_resolvable(fixture: EvalFixture, draft: DraftEnvelope) -> bool:
    if not draft["suggested_action"] or not draft["citations"]:
        return False
    _status, errors = validate_draft(
        draft,
        citation_sources=[fixture.source.model_dump(mode="python")],
    )
    return not _CITATION_ERRORS.intersection(errors)


async def _evaluate_case(fixture: EvalFixture) -> EvalCaseResult:
    try:
        result = await intake_graph.ainvoke(_state(fixture))
        if type(result) is not dict:
            raise TypeError("intake graph result is not a plain dict")
        draft = cast(IntakeState, result).get("draft")
        if draft is None:
            raise ValueError("intake graph produced no draft")
        facts_grounded = _facts_grounded(fixture, draft)
        urgency_in_range = _urgency_in_range(fixture, draft)
        citations_resolvable = _citations_resolvable(fixture, draft)
        return EvalCaseResult(
            fixture_id=fixture.id,
            passed=facts_grounded and urgency_in_range and citations_resolvable,
            facts_grounded=facts_grounded,
            urgency_in_range=urgency_in_range,
            citations_resolvable=citations_resolvable,
            provider=draft["provider"],
        )
    except Exception as error:
        return EvalCaseResult(
            fixture_id=fixture.id,
            passed=False,
            facts_grounded=False,
            urgency_in_range=False,
            citations_resolvable=False,
            provider="unavailable",
            failure=type(error).__name__,
        )


async def evaluate() -> EvalReport:
    cases = tuple(
        [await _evaluate_case(fixture) for fixture in load_fixtures()]
    )
    return EvalReport(cases=cases)


def render_report(report: EvalReport) -> str:
    provider_names = sorted({case.provider for case in report.cases})
    lines = [
        "SafeLoop intake evaluation",
        f"Provider: {', '.join(provider_names)}",
        f"Pass rate: {report.passed}/{report.total} ({report.pass_rate:.0%})",
    ]
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        detail = (
            f"facts={case.facts_grounded} urgency={case.urgency_in_range} "
            f"citations={case.citations_resolvable}"
        )
        if case.failure is not None:
            detail = f"failure={case.failure}"
        lines.append(f"{status} {case.fixture_id} {detail}")
    return "\n".join(lines)
