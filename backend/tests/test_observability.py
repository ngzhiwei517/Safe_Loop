"""Prove slow and failed requests are diagnosable from structured records."""

from __future__ import annotations

import asyncio
from io import StringIO
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability import (
    ERROR_ID_HEADER,
    REQUEST_ID_HEADER,
    ErrorRegistry,
    JsonFormatter,
    LatencyRegistry,
    RequestObservabilityMiddleware,
)


def test_json_formatter_emits_typed_context() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.json")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info(
        "ai_run_completed",
        extra={
            "request_id": "request-json",
            "report_id": "report-1",
            "tokens_in": 12,
            "cost_usd": 0.01,
        },
    )

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "ai_run_completed"
    assert payload["request_id"] == "request-json"
    assert payload["report_id"] == "report-1"
    assert payload["tokens_in"] == 12
    assert payload["cost_usd"] == 0.01


def test_slow_and_failed_requests_have_correlated_logs_and_metrics(
    caplog,
) -> None:  # type: ignore[no-untyped-def]
    registry = LatencyRegistry(max_samples=10)
    app = FastAPI()
    app.add_middleware(
        RequestObservabilityMiddleware,
        slow_request_ms=1,
        registry=registry,
    )

    @app.get("/slow/{item_id}")
    async def slow(item_id: str) -> dict[str, str]:
        await asyncio.sleep(0.005)
        return {"id": item_id}

    @app.get("/failed")
    async def failed() -> None:
        raise RuntimeError("diagnostic fixture")

    with caplog.at_level(logging.INFO):
        slow_response = TestClient(app).get(
            "/slow/one",
            headers={REQUEST_ID_HEADER: "request-slow"},
        )
    assert slow_response.status_code == 200
    assert slow_response.headers[REQUEST_ID_HEADER] == "request-slow"
    slow_record = next(
        record
        for record in caplog.records
        if record.msg == "request_completed" and record.request_id == "request-slow"
    )
    assert slow_record.endpoint == "/slow/{item_id}"
    assert slow_record.slow is True
    assert slow_record.latency_ms >= 1

    caplog.clear()
    with caplog.at_level(logging.ERROR):
        failed_response = TestClient(app).get(
            "/failed",
            headers={REQUEST_ID_HEADER: "request-failed"},
        )
    assert failed_response.status_code == 500
    assert failed_response.json()["detail"]["code"] == "internal_error"
    assert failed_response.headers[REQUEST_ID_HEADER] == "request-failed"
    error_id = failed_response.headers[ERROR_ID_HEADER]
    failure = next(record for record in caplog.records if record.msg == "request_failed")
    assert failure.request_id == "request-failed"
    assert failure.error_id == error_id
    assert failure.error_type == "RuntimeError"
    completion = next(
        record for record in caplog.records if record.msg == "request_completed"
    )
    assert completion.error_id == error_id
    assert completion.status_code == 500

    snapshot = registry.snapshot()
    assert snapshot["GET /slow/{item_id}"]["count"] == 1
    assert snapshot["GET /failed"]["error_count"] == 1


def test_error_registry_is_bounded() -> None:
    registry = ErrorRegistry(max_recent=2)
    for index in range(3):
        registry.track("fixture", RuntimeError(str(index)))
    snapshot = registry.snapshot()
    recent = snapshot["recent"]
    assert isinstance(recent, list)
    assert len(recent) == 2
    assert snapshot["total"] == 3
