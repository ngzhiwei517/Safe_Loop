"""Prove lesson generation fails closed before durable state can advance."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import pytest

from app.ai.lesson_graph import LessonState
from app.services import lesson_service

REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")


def state() -> LessonState:
    return {
        "report_id": str(REPORT_ID),
        "verified_case": {
            "corrective_action": "Install and secure the missing guardrail.",
            "completed_note": "The guardrail was installed.",
            "verification_notes": "The guardrail passed the final inspection.",
            "verification_checklist": {"hazard_removed": True},
            "target_activity": "Formwork",
            "target_location": "Level 6",
            "evidence_captions": [],
            "evidence_count": 0,
        },
        "retrieved_chunks": [],
        "case_summary": [],
        "procedure_sources": [],
        "briefing_en_sections": [],
        "briefing_zh_cn_sections": [],
        "briefing_en": "",
        "briefing_zh_cn": "",
        "quiz_questions": [],
    }


def test_graph_failure_logs_and_never_persists_or_advances(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    loaded = lesson_service._LoadedLesson(state(), "guardrail formwork")
    persisted = False

    async def fake_load(_: UUID) -> lesson_service._LoadedLesson:
        return loaded

    async def fail_graph(_: lesson_service._LoadedLesson) -> LessonState:
        raise RuntimeError("graph failed")

    async def must_not_persist(*_: object) -> bool:
        nonlocal persisted
        persisted = True
        return True

    monkeypatch.setattr(lesson_service, "_load_lesson", fake_load)
    monkeypatch.setattr(lesson_service, "_invoke_graph", fail_graph)
    monkeypatch.setattr(lesson_service, "_persist_lesson", must_not_persist)

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(lesson_service.run_lesson(REPORT_ID))

    assert result is False
    assert persisted is False
    assert "lesson_graph_failed" in caplog.text


def test_known_profile_names_are_removed_before_graph_input() -> None:
    redacted = lesson_service._redact_names(
        "Daniel Tan installed the guardrail. daniel tan checked it.",
        ["Daniel Tan"],
    )

    assert redacted == "a worker installed the guardrail. a worker checked it."


def test_short_profile_name_does_not_corrupt_a_safety_term() -> None:
    redacted = lesson_service._redact_names(
        "Li checked the lifting point.",
        ["Li"],
    )

    assert redacted == "a worker checked the lifting point."
