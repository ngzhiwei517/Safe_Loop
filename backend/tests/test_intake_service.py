"""Prove background intake fails closed before touching durable state."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import pytest

from app.ai.intake_graph import IntakeState
from app.ai.usage import record_ai_usage
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
        "retrieved_chunks": [],
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
        result = asyncio.run(
            intake_service.run_intake(REPORT_ID, "request-intake-failed")
        )

    assert result is False
    assert persisted is False
    assert loaded.status is ReportStatus.SUBMITTED
    failure = next(record for record in caplog.records if record.msg == "ai_run_failed")
    assert failure.request_id == "request-intake-failed"
    assert failure.report_id == str(REPORT_ID)
    assert failure.graph == "intake"
    assert failure.provider == "stub"
    assert failure.tokens_in == 0
    assert failure.tokens_out == 0
    assert failure.cost_usd == 0.0
    assert failure.validation_result == "failed"
    assert failure.error_id


def test_successful_run_propagates_request_id_and_logs_aggregate_usage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    loaded = intake_service._LoadedIntake(ReportStatus.SUBMITTED, _state())

    async def fake_load(_: UUID) -> intake_service._LoadedIntake:
        return loaded

    async def fake_graph(state: IntakeState) -> IntakeState:
        assert state["request_id"] == "request-intake-ok"
        record_ai_usage(
            provider="stub",
            provider_ref="stub-call-1",
            operation="complete:extract_facts",
            latency_ms=12,
            tokens_in=15,
            tokens_out=9,
            cost_usd=0.0,
        )
        return state

    async def fake_persist(
        *_: object,
    ) -> intake_service._PersistedIntake:
        return intake_service._PersistedIntake(True, "valid")

    monkeypatch.setattr(intake_service, "_load_intake", fake_load)
    monkeypatch.setattr(intake_service, "_invoke_graph", fake_graph)
    monkeypatch.setattr(intake_service, "_persist_result", fake_persist)

    with caplog.at_level(logging.INFO):
        result = asyncio.run(intake_service.run_intake(REPORT_ID, "request-intake-ok"))

    assert result is True
    completed = next(
        record for record in caplog.records if record.msg == "ai_run_completed"
    )
    assert completed.request_id == "request-intake-ok"
    assert completed.report_id == str(REPORT_ID)
    assert completed.graph == "intake"
    assert completed.provider == "stub"
    assert completed.provider_refs == ["stub-call-1"]
    assert completed.provider_latency_ms == 12
    assert completed.tokens_in == 15
    assert completed.tokens_out == 9
    assert completed.cost_usd == 0.0
    assert completed.validation_result == "valid"
    assert completed.outcome == "persisted"
