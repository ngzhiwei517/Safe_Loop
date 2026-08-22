"""Keep the checked-in real-model evaluation deterministic under the CI stub."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.ai.eval.runner import (
    MINIMUM_PASS_RATE,
    evaluate,
    load_fixtures,
    render_report,
)
from app.ai import llm_provider


def test_eval_corpus_has_exactly_fifteen_reports_and_two_code_switched_cases() -> None:
    fixtures = load_fixtures()

    assert len(fixtures) == 15
    assert sum(
        fixture.lang_original == "zh-CN"
        and any(
            term in fixture.description_original.casefold()
            for term in ("guardrail", "formwork", "electrical", "cable")
        )
        for fixture in fixtures
    ) >= 2
    assert {fixture.lang_original for fixture in fixtures} == {"en", "zh-CN"}
    assert any(fixture.activity is None for fixture in fixtures)
    assert any(fixture.activity is not None for fixture in fixtures)


def test_mandarin_eval_markers_cover_the_english_pivot_language() -> None:
    fixtures = load_fixtures()
    mandarin_fixtures = [
        fixture for fixture in fixtures if fixture.lang_original == "zh-CN"
    ]

    assert all(
        any(any(character.isascii() and character.isalpha() for character in marker)
            for marker in fixture.expected_fact_markers)
        for fixture in mandarin_fixtures
    )
    assert all(
        any(any(character.isascii() and character.isalpha() for character in marker)
            for marker in fixture.forbidden_fact_markers)
        for fixture in mandarin_fixtures
    )


def test_stub_eval_clears_the_required_pass_rate_without_network() -> None:
    report = asyncio.run(evaluate())

    assert report.total == 15
    assert report.pass_rate >= MINIMUM_PASS_RATE
    assert all(case.provider == "stub" for case in report.cases)
    rendered = render_report(report)
    assert f"{report.passed}/{report.total}" in rendered


def test_vendor_sdk_is_isolated_to_the_real_provider_module() -> None:
    ai_root = Path(llm_provider.__file__).parent
    offenders = [
        path
        for path in ai_root.rglob("*.py")
        if path != Path(llm_provider.__file__)
        and ("google.genai" in path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
