"""Prove the first intake graph preserves language and separates inference from fact."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Literal, cast

import pytest

from app.ai import intake_graph as intake_module
from app.ai.intake_graph import IntakeState, intake_graph, translate


def state(
    description: str,
    *,
    locale: Literal["en", "zh-CN"] = "en",
    location: str | None = "Level 6 edge",
    activity: str | None = "Formwork",
) -> IntakeState:
    return {
        "report_id": "10000000-0000-0000-0000-000000000001",
        "lang_original": locale,
        "description_original": description,
        "description_en": None,
        "location": location,
        "activity": activity,
        "prior_answers": [],
        "round": 0,
        "observed_facts": [],
        "assumptions": [],
        "missing_information": [],
        "questions": [],
        "draft": None,
    }


def run(input_state: IntakeState) -> dict[str, object]:
    result = asyncio.run(intake_graph.ainvoke(dict(input_state)))
    assert type(result) is dict
    return cast(dict[str, object], result)


def test_complete_mandarin_report_has_english_and_no_gaps() -> None:
    original = "六楼模板边缘没有护栏，工人正在附近搬运材料。"
    result = run(state(original, locale="zh-CN", activity="Moving materials"))

    assert result["description_original"] == original
    assert isinstance(result["description_en"], str)
    assert result["description_en"] != original
    assert result["missing_information"] == []


def test_vague_report_has_decision_changing_gaps() -> None:
    result = run(state("Unsafe", location=None, activity=None))

    assert result["missing_information"] == ["hazard_detail", "location", "activity"]


def test_inference_is_an_assumption_and_never_an_observed_fact() -> None:
    result = run(
        state("The guardrail is missing. The worker was careless.")
    )
    observed = cast(list[str], result["observed_facts"])
    assumptions = cast(list[str], result["assumptions"])

    assert any("careless" in item.casefold() for item in assumptions)
    assert all("careless" not in item.casefold() for item in observed)
    assert any("guardrail" in item.casefold() for item in observed)


def test_code_switched_trade_terms_survive_translation() -> None:
    original = "六楼 formwork 边缘没有 guardrail。"
    result = run(state(original, locale="zh-CN"))
    translated = cast(str, result["description_en"])

    assert "formwork" in translated
    assert "guardrail" in translated
    assert result["description_original"] == original


def test_english_translation_is_a_no_op_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider_must_not_be_loaded() -> None:
        raise AssertionError("provider should not be loaded for English")

    monkeypatch.setattr(intake_module, "get_provider", provider_must_not_be_loaded)
    input_state = state("The guardrail is missing.")
    update = asyncio.run(translate(input_state))

    assert update == {"description_en": input_state["description_original"]}


def test_ai_package_never_imports_asyncpg() -> None:
    ai_directory = Path(intake_module.__file__).parent
    offenders: list[str] = []
    for path in ai_directory.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                imported.name == "asyncpg" or imported.name.startswith("asyncpg.")
                for imported in node.names
            ):
                offenders.append(str(path))
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "asyncpg" or node.module.startswith("asyncpg.")
            ):
                offenders.append(str(path))
    assert offenders == []
