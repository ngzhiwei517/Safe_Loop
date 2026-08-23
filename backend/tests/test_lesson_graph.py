"""Prove one stub lesson run is bilingual, sourced, anonymous, and quiz-complete."""

from __future__ import annotations

import asyncio
from typing import cast

from app.ai.lesson_graph import (
    MAX_BRIEFING_EN_WORDS,
    MAX_BRIEFING_ZH_CHARACTERS,
    LessonState,
    lesson_graph,
)


def lesson_state() -> LessonState:
    return {
        "report_id": "10000000-0000-0000-0000-000000000001",
        "verified_case": {
            "corrective_action": (
                "Mr Daniel Tan installed the missing guardrail and secured both anchors."
            ),
            "completed_note": "The upper and lower anchors were tightened.",
            "verification_notes": "Both anchors passed the final pull test.",
            "verification_checklist": {"hazard_removed": True},
            "target_activity": "Formwork",
            "target_location": "Level 6 east edge",
            "evidence_captions": ["Completed guardrail at the east edge"],
            "evidence_count": 1,
        },
        "retrieved_chunks": [
            {
                "content": (
                    "Workers must install guardrails before work starts. "
                    "Inspect every anchor before use."
                ),
                "document_id": "20000000-0000-0000-0000-000000000001",
                "doc_ref": "WAH-001",
                "revision": "3",
                "section": "4.2",
                "page": 7,
                "similarity": 0.92,
            },
            {
                "content": "高处作业前必须检查防护栏。防护栏必须牢固。",
                "document_id": "20000000-0000-0000-0000-000000000002",
                "doc_ref": "高处-001",
                "revision": "2",
                "section": "4.2",
                "page": 8,
                "similarity": 0.9,
            },
        ],
        "case_summary": [],
        "procedure_sources": [],
        "briefing_en_sections": [],
        "briefing_zh_cn_sections": [],
        "briefing_en": "",
        "briefing_zh_cn": "",
        "quiz_questions": [],
    }


def test_lesson_graph_produces_both_locales_and_exactly_three_questions() -> None:
    result = asyncio.run(lesson_graph.ainvoke(lesson_state()))
    assert type(result) is dict
    output = cast(LessonState, result)

    assert output["briefing_en"].strip()
    assert output["briefing_zh_cn"].strip()
    assert len(output["briefing_en"].split()) <= MAX_BRIEFING_EN_WORDS
    assert len(output["briefing_zh_cn"]) <= MAX_BRIEFING_ZH_CHARACTERS
    assert "防护栏" in output["briefing_zh_cn"]
    assert "Daniel" not in output["briefing_en"]
    assert "Daniel" not in output["briefing_zh_cn"]

    assert len(output["quiz_questions"]) == 3
    for question in output["quiz_questions"]:
        assert question["question"]["en"].strip()
        assert question["question"]["zh_cn"].strip()
        assert question["explanation"]["en"].strip()
        assert question["explanation"]["zh_cn"].strip()
        assert len(question["options"]) == 4
        assert all(option["en"].strip() for option in question["options"])
        assert all(option["zh_cn"].strip() for option in question["options"])
        assert 0 <= question["correct_option"] < 4
        assert question["source_refs"]


def test_lesson_graph_returns_plain_serialisable_state() -> None:
    result = asyncio.run(lesson_graph.ainvoke(lesson_state()))

    assert type(result) is dict
    assert isinstance(result["case_summary"], list)
    assert isinstance(result["procedure_sources"], list)
    assert isinstance(result["quiz_questions"], list)
