"""Verify transcription is deterministic, regional, resilient, and report-neutral."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from typing import cast
from uuid import UUID

from fastapi.responses import JSONResponse
from google.genai import types
import httpx
import pytest

from app.ai import transcription as transcription_module
from app.ai.eval_asr.runner import edit_distance, load_fixtures
from app.ai.provider import ProviderConfigurationError
from app.ai.transcription import (
    MAX_RETRIES,
    GeminiTranscription,
    GeminiTranscriptionConfig,
    StubTranscription,
    Transcript,
    TranscriptionFailure,
    _VertexClient,
    _make_vertex_client,
)
from app.api import transcription as transcription_api
from app.api.transcription import TranscribeRequest
from app.config import DEFAULT_VERTEX_LOCATION, get_settings
from app.domain.enums import ActorType, Role
from app.services.report_service import Actor
from app.services.transcription_service import AudioMedia, download_audio

REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
MEDIA_ID = UUID("70000000-0000-0000-0000-000000000001")
REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")


@dataclass
class FakeResponse:
    text: str | None
    response_id: str | None = "vertex-asr-1"
    model_version: str | None = "gemini-test"


class FakeModels:
    def __init__(self, results: list[FakeResponse | Exception]) -> None:
        self.results = results
        self.calls: list[tuple[str, object, object]] = []

    async def generate_content(
        self,
        *,
        model: str,
        contents: object,
        config: object,
    ) -> FakeResponse:
        index = len(self.calls)
        self.calls.append((model, contents, config))
        result = self.results[min(index, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class FakeAsyncClient:
    models: FakeModels


@dataclass
class FakeClient:
    aio: FakeAsyncClient


def config(**overrides: object) -> GeminiTranscriptionConfig:
    values: dict[str, object] = {
        "project_id": "safeloop-test",
        "location": DEFAULT_VERTEX_LOCATION,
        "model": "gemini-test",
        "circuit_failure_threshold": 3,
        "circuit_reset_seconds": 60.0,
    }
    values.update(overrides)
    return GeminiTranscriptionConfig(**values)  # type: ignore[arg-type]


def gemini_with(
    models: FakeModels,
    **overrides: object,
) -> GeminiTranscription:
    return GeminiTranscription(
        config(**overrides),
        client=cast(_VertexClient, FakeClient(FakeAsyncClient(models))),
    )


def test_stub_is_deterministic_and_keyed_by_audio_bytes() -> None:
    provider = StubTranscription()
    first = asyncio.run(provider.transcribe(b"audio-one", "audio/webm", "zh-CN"))
    repeated = asyncio.run(provider.transcribe(b"audio-one", "audio/webm", "zh-CN"))
    changed = asyncio.run(provider.transcribe(b"audio-two", "audio/webm", "zh-CN"))

    assert isinstance(first, Transcript)
    assert first == repeated
    assert isinstance(changed, Transcript)
    assert first.provider_ref != changed.provider_ref
    assert first.text != changed.text
    assert first.detected_locale == "zh-CN"


def test_stub_rejects_empty_or_unsupported_audio_without_raising() -> None:
    result = asyncio.run(
        StubTranscription().transcribe(b"", "application/octet-stream", "en-SG")
    )

    assert isinstance(result, TranscriptionFailure)
    assert result.code == "invalid_audio"
    assert result.retryable is False


def test_gemini_preserves_detected_locale_when_it_disagrees_with_hint() -> None:
    models = FakeModels(
        [
            FakeResponse(
                json.dumps(
                    {
                        "text": "六楼 formwork 边缘没有 guardrail",
                        "detected_locale": "mul",
                        "confidence": 0.92,
                        "duration_ms": 30000,
                    }
                )
            )
        ]
    )
    result = asyncio.run(
        gemini_with(models).transcribe(b"audio", "audio/mp4", "en-SG")
    )

    assert isinstance(result, Transcript)
    assert result.detected_locale == "mul"
    assert result.text == "六楼 formwork 边缘没有 guardrail"
    assert result.duration_ms == 30000
    _, contents, request_config = models.calls[0]
    assert isinstance(contents, list)
    prompt = contents[0].parts[0].text
    assert "Do not summarise, translate" in prompt
    assert "weak recognition hint only" in prompt
    assert "en-SG" in prompt
    assert isinstance(request_config, types.GenerateContentConfig)
    assert request_config.response_mime_type == "application/json"


def test_gemini_retries_twice_with_jitter_then_returns_success() -> None:
    models = FakeModels(
        [
            RuntimeError("temporary one"),
            RuntimeError("temporary two"),
            FakeResponse(
                '{"text":"hazard","detected_locale":"en-SG",'
                '"confidence":0.8,"duration_ms":1000}'
            ),
        ]
    )
    delays: list[float] = []

    async def capture_sleep(delay: float) -> None:
        delays.append(delay)

    provider = GeminiTranscription(
        config(),
        client=cast(_VertexClient, FakeClient(FakeAsyncClient(models))),
        sleep=capture_sleep,
        random_source=lambda: 0.5,
    )
    result = asyncio.run(provider.transcribe(b"audio", "audio/mpeg", "en-SG"))

    assert isinstance(result, Transcript)
    assert len(models.calls) == MAX_RETRIES + 1
    assert delays == [0.25, 0.5]


def test_circuit_breaker_returns_typed_failure_instead_of_raising() -> None:
    models = FakeModels([RuntimeError("provider down")])

    async def no_sleep(_: float) -> None:
        return None

    provider = GeminiTranscription(
        config(circuit_failure_threshold=1),
        client=cast(_VertexClient, FakeClient(FakeAsyncClient(models))),
        sleep=no_sleep,
        clock=lambda: 0.0,
    )
    failed = asyncio.run(provider.transcribe(b"audio", "audio/webm", "en-SG"))
    calls_after_failure = len(models.calls)
    circuit_open = asyncio.run(
        provider.transcribe(b"audio", "audio/webm", "en-SG")
    )

    assert isinstance(failed, TranscriptionFailure)
    assert failed.code == "provider_unavailable"
    assert isinstance(circuit_open, TranscriptionFailure)
    assert circuit_open.code == "circuit_open"
    assert len(models.calls) == calls_after_failure


def test_vertex_client_is_regional_and_disables_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_client = FakeClient(FakeAsyncClient(FakeModels([])))

    def capture_client(**kwargs: object) -> FakeClient:
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr(transcription_module.genai, "Client", capture_client)
    assert _make_vertex_client(config()) is fake_client
    assert captured["vertexai"] is True
    assert captured["project"] == "safeloop-test"
    assert captured["location"] == "asia-southeast1"
    options = captured["http_options"]
    assert isinstance(options, types.HttpOptions)
    assert options.timeout == 30_000
    assert options.retry_options is not None
    assert options.retry_options.attempts == 1
    assert config().endpoint == "https://asia-southeast1-aiplatform.googleapis.com"


def test_global_or_non_singapore_vertex_location_is_rejected() -> None:
    client = cast(_VertexClient, FakeClient(FakeAsyncClient(FakeModels([]))))

    for location in ("global", "us-central1"):
        with pytest.raises(ProviderConfigurationError):
            GeminiTranscription(config(location=location), client=client)


def test_private_audio_download_uses_service_key_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-test-key")
    get_settings.cache_clear()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"stored-audio")

    media = AudioMedia(
        MEDIA_ID,
        REPORT_ID,
        f"{REPORTER_ID}/report/audio.webm",
        "audio/webm",
    )

    async def exercise() -> bytes:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await download_audio(media, client=client)

    try:
        assert asyncio.run(exercise()) == b"stored-audio"
    finally:
        get_settings.cache_clear()
    assert len(requests) == 1
    assert requests[0].url.path.endswith(
        f"/storage/v1/object/report-audio/{REPORTER_ID}/report/audio.webm"
    )
    assert requests[0].headers["authorization"] == "Bearer service-test-key"


def test_transcribe_endpoint_rate_limits_persists_success_and_returns_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    media = AudioMedia(MEDIA_ID, REPORT_ID, "owner/report/audio.webm", "audio/webm")

    async def enforce(**values: object) -> None:
        calls.append(f"limit:{values['scope']}:{values['error_code']}")

    async def get_media(*_: object) -> AudioMedia:
        calls.append("media")
        return media

    async def download(_: AudioMedia) -> bytes:
        calls.append("download")
        return b"audio-fixture"

    async def persist(*_: object, **__: object) -> dict[str, object]:
        calls.append("persist")
        return {"id": "transcript"}

    monkeypatch.setattr(transcription_api, "enforce_rate_limit", enforce)
    monkeypatch.setattr(transcription_api, "get_audio_media", get_media)
    monkeypatch.setattr(transcription_api, "download_audio", download)
    monkeypatch.setattr(transcription_api, "persist_transcript", persist)
    monkeypatch.setattr(
        transcription_api, "get_transcription_provider", StubTranscription
    )
    result = asyncio.run(
        transcription_api.post_transcribe(
            TranscribeRequest(media_id=MEDIA_ID, hint_locale="zh-CN"),
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
    )

    assert isinstance(result, dict)
    assert result["provider"] == "stub"
    assert result["detected_locale"] == "zh-CN"
    assert result["transcript_id"] == "transcript"
    assert result["meets_confidence_threshold"] is True
    assert calls == [
        "limit:transcription:transcription_rate_limited",
        "media",
        "download",
        "persist",
    ]


def test_provider_failure_is_typed_and_never_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = AudioMedia(MEDIA_ID, REPORT_ID, "owner/report/audio.webm", "audio/webm")

    async def no_limit(**_: object) -> None:
        return None

    async def get_media(*_: object) -> AudioMedia:
        return media

    async def download(_: AudioMedia) -> bytes:
        return b"audio-fixture"

    class FailedProvider:
        async def transcribe(self, *_: object) -> TranscriptionFailure:
            return TranscriptionFailure(
                code="circuit_open",
                provider="vertex-gemini",
                model="gemini-test",
                retryable=True,
                latency_ms=0,
            )

    async def unexpected_persist(*_: object, **__: object) -> None:
        raise AssertionError("failed transcription must not be persisted")

    monkeypatch.setattr(transcription_api, "enforce_rate_limit", no_limit)
    monkeypatch.setattr(transcription_api, "get_audio_media", get_media)
    monkeypatch.setattr(transcription_api, "download_audio", download)
    monkeypatch.setattr(
        transcription_api, "get_transcription_provider", FailedProvider
    )
    monkeypatch.setattr(
        transcription_api, "persist_transcript", unexpected_persist
    )
    result = asyncio.run(
        transcription_api.post_transcribe(
            TranscribeRequest(media_id=MEDIA_ID),
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        )
    )

    assert isinstance(result, JSONResponse)
    assert result.status_code == 503
    assert json.loads(result.body)["detail"]["code"] == "circuit_open"


def test_asr_corpus_and_error_metric_cover_requested_conditions() -> None:
    fixtures = load_fixtures()

    assert len(fixtures) == 10
    assert {fixture.category for fixture in fixtures} == {
        "mandarin",
        "english",
        "code-switched",
        "noisy-mandarin",
        "noisy-english",
    }
    assert all(fixture.path.stat().st_size > 20_000 for fixture in fixtures)
    assert edit_distance(list("安全"), list("安生")) == 1
    assert edit_distance(["fire", "exit"], ["exit"]) == 1
