"""Run the first pure intake stages without persisting or advancing a report."""

from __future__ import annotations

import re
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app.ai.provider import JsonValue, get_provider


class PriorAnswer(TypedDict):
    """Keep prior human clarification text JSON-serialisable."""

    question: str
    answer: str


class IntakeQuestion(TypedDict):
    """Reserve the next step's question shape without composing one here."""

    gap: str
    text: str


class IntakeState(TypedDict):
    """Carry only plain data across durable, independently restartable graph runs."""

    report_id: str
    lang_original: Literal["en", "zh-CN"]
    description_original: str
    description_en: str | None
    location: str | None
    activity: str | None
    prior_answers: list[PriorAnswer]
    round: int
    observed_facts: list[str]
    assumptions: list[str]
    missing_information: list[str]
    questions: list[IntakeQuestion]
    draft: dict[str, JsonValue] | None


def _text(variables: dict[str, object], name: str) -> str:
    value = variables.get(name)
    return value if isinstance(value, str) else ""


def _string_list(variables: dict[str, object], name: str) -> list[str]:
    value = variables.get(name)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


_TRANSLATION_REPLACEMENTS = (
    ("六楼", "Level 6 "),
    ("七楼", "Level 7 "),
    ("模板", "formwork "),
    ("边缘没有护栏", "edge has no guardrail "),
    ("没有护栏", "has no guardrail "),
    ("边缘", "edge "),
    ("没有", "has no "),
    ("护栏", "guardrail"),
    ("工人", "worker "),
    ("正在", "is "),
    ("附近", "nearby "),
    ("搬运材料", "moving materials"),
    ("脚手架", "scaffold"),
    ("松动", "loose"),
)


def _stub_translate(source: str) -> str:
    translated = source
    for original, replacement in _TRANSLATION_REPLACEMENTS:
        translated = translated.replace(original, replacement)
    translated = translated.replace("，", ", ").replace("。", ".")
    translated = re.sub(r"\s+([,.])", r"\1", translated)
    return re.sub(r"\s+", " ", translated).strip()


_ASSUMPTION_MARKERS = (
    "careless",
    "reckless",
    "probably",
    "likely",
    "must have",
    "seems",
    "appears",
    "疏忽",
    "粗心",
)


def _split_observation(description: str) -> tuple[list[str], list[str]]:
    segments = [
        segment.strip(" .;。；,，")
        for segment in re.split(
            r"(?<=[.;。；])\s*|\s+(?:and|but)\s+|[,，]",
            description,
            flags=re.IGNORECASE,
        )
        if segment.strip(" .;。；,，")
    ]
    observed: list[str] = []
    assumptions: list[str] = []
    for segment in segments:
        destination = (
            assumptions
            if any(marker in segment.casefold() for marker in _ASSUMPTION_MARKERS)
            else observed
        )
        destination.append(segment)
    return observed, assumptions


_SPECIFIC_HAZARD_TERMS = (
    "guardrail",
    "edge",
    "scaffold",
    "blocked",
    "loose",
    "exposed",
    "leak",
    "cable",
    "fire exit",
    "护栏",
    "边缘",
    "脚手架",
)
_LOCATION_TERMS = ("level", "floor", "zone", "tower", "block", "楼", "层", "区")
_ACTIVITY_TERMS = (
    "formwork",
    "lifting",
    "welding",
    "scaffold",
    "moving materials",
    "模板",
    "吊装",
    "焊接",
    "脚手架",
    "搬运",
)


def _stub_gaps(
    description: str,
    location: str,
    activity: str,
    observed_facts: list[str],
) -> list[str]:
    normalised = description.casefold().strip()
    gaps: list[str] = []
    if (
        not observed_facts
        or len(normalised.split()) < 3
        or not any(term in normalised for term in _SPECIFIC_HAZARD_TERMS)
    ):
        gaps.append("hazard_detail")
    if not location.strip() and not any(term in normalised for term in _LOCATION_TERMS):
        gaps.append("location")
    if not activity.strip() and not any(term in normalised for term in _ACTIVITY_TERMS):
        gaps.append("activity")
    return gaps


class TranslationResult(BaseModel):
    description_en: str

    @classmethod
    def stub_fixture(cls, variables: dict[str, object]) -> dict[str, JsonValue]:
        return {"description_en": _stub_translate(_text(variables, "description_original"))}


class FactExtractionResult(BaseModel):
    observed_facts: list[str]
    assumptions: list[str]

    @classmethod
    def stub_fixture(cls, variables: dict[str, object]) -> dict[str, JsonValue]:
        observed, assumptions = _split_observation(_text(variables, "description"))
        observed_json: list[JsonValue] = list(observed)
        assumptions_json: list[JsonValue] = list(assumptions)
        return {
            "observed_facts": observed_json,
            "assumptions": assumptions_json,
        }


class CompletenessResult(BaseModel):
    missing_information: list[str]

    @classmethod
    def stub_fixture(cls, variables: dict[str, object]) -> dict[str, JsonValue]:
        gaps: list[JsonValue] = list(
            _stub_gaps(
                _text(variables, "description"),
                _text(variables, "location"),
                _text(variables, "activity"),
                _string_list(variables, "observed_facts"),
            )
        )
        return {
            "missing_information": gaps,
        }


def _result_string(data: dict[str, JsonValue], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str):
        raise TypeError("provider result field is not a string")
    return value


def _result_strings(data: dict[str, JsonValue], name: str) -> list[str]:
    value = data.get(name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("provider result field is not a string list")
    return cast(list[str], value)


async def translate(state: IntakeState) -> dict[str, object]:
    """Preserve English verbatim and derive a separate pivot for Mandarin input."""
    if state["lang_original"] == "en":
        return {"description_en": state["description_original"]}
    result = await get_provider().complete(
        "translate_intake",
        {
            "lang_original": state["lang_original"],
            "description_original": state["description_original"],
        },
        schema=TranslationResult,
    )
    return {"description_en": _result_string(result.data, "description_en")}


async def extract_facts(state: IntakeState) -> dict[str, object]:
    """Keep observations and interpretations in separate state channels."""
    description = state["description_en"] or state["description_original"]
    result = await get_provider().complete(
        "extract_facts",
        {
            "description": description,
            "location": state["location"],
            "activity": state["activity"],
            "prior_answers": state["prior_answers"],
        },
        schema=FactExtractionResult,
    )
    return {
        "observed_facts": _result_strings(result.data, "observed_facts"),
        "assumptions": _result_strings(result.data, "assumptions"),
    }


async def assess_completeness(state: IntakeState) -> dict[str, object]:
    """Identify only gaps material to a reviewer's next decision."""
    description = state["description_en"] or state["description_original"]
    result = await get_provider().complete(
        "assess_completeness",
        {
            "description": description,
            "location": state["location"],
            "activity": state["activity"],
            "observed_facts": state["observed_facts"],
            "assumptions": state["assumptions"],
        },
        schema=CompletenessResult,
    )
    return {
        "missing_information": _result_strings(
            result.data,
            "missing_information",
        )
    }


def build_intake_graph() -> CompiledStateGraph[
    IntakeState,
    None,
    IntakeState,
    IntakeState,
]:
    """Compile only the three nodes included in this phase step."""
    builder: StateGraph[IntakeState, None, IntakeState, IntakeState] = StateGraph(
        IntakeState
    )
    builder.add_node("translate", translate)
    builder.add_node("extract_facts", extract_facts)
    builder.add_node("assess_completeness", assess_completeness)
    builder.add_edge(START, "translate")
    builder.add_edge("translate", "extract_facts")
    builder.add_edge("extract_facts", "assess_completeness")
    builder.add_edge("assess_completeness", END)
    return builder.compile(name="safeloop_intake_first_pass")


intake_graph = build_intake_graph()
