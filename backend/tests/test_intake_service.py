"""Prove background intake fails closed before touching durable state."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import pytest

from app.ai.intake_graph import IntakeState
from app.domain.enums import ReportStatus
from app.services import intake_service

REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")


def _state() -> IntakeState:
    return {
        "report_id": str(REPORT_ID),
        "lang_original": "en",
        "preferred_lang": "en",
        "description_original": "Unsafe",
        "description_en": None,
        "location": None,
        "activity": None,
        "prior_answers": [],
        "round": 0,
        "observed_facts": [],
        "assumptions": [],
        "missing_information": [],
        "questions": [],
        "draft": None,
    }


def test_graph_failure_logs_and_never_persists_or_advances(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    loaded = intake_service._LoadedIntake(ReportStatus.SUBMITTED, _state())
    persisted = False

    async def fake_load(_: UUID) -> intake_service._LoadedIntake:
        return loaded

    async def fail_graph(_: IntakeState) -> IntakeState:
        raise RuntimeError("graph failed")

    async def must_not_persist(*_: object) -> bool:
        nonlocal persisted
        persisted = True
        return True

    monkeypatch.setattr(intake_service, "_load_intake", fake_load)
    monkeypatch.setattr(intake_service, "_invoke_graph", fail_graph)
    monkeypatch.setattr(intake_service, "_persist_result", must_not_persist)

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(intake_service.run_intake(REPORT_ID))

    assert result is False
    assert persisted is False
    assert loaded.status is ReportStatus.SUBMITTED
    assert "intake_graph_failed" in caplog.text
