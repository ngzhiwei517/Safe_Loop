"""Transcribe stored audio through a deterministic stub or regional Vertex AI."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import logging
import random
import time
from typing import Final, Literal, Protocol, TypeAlias, cast

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.provider import ProviderConfigurationError
from app.config import DEFAULT_VERTEX_LOCATION, Settings, get_settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS: Final = 30.0
MAX_RETRIES: Final = 2
RETRY_BASE_SECONDS: Final = 0.25
SUPPORTED_AUDIO_MIME_TYPES: Final = frozenset(
    {"audio/webm", "audio/mp4", "audio/mpeg", "audio/wav"}
)

_Sleep = Callable[[float], Awaitable[None]]
_Clock = Callable[[], float]
_Random = Callable[[], float]
FailureCode: TypeAlias = Literal[
    "circuit_open",
    "invalid_audio",
    "invalid_response",
    "provider_misconfigured",
    "provider_unavailable",
]


class Transcript(BaseModel):
    """Auditable transcription result returned to the caller and persistence layer."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    detected_locale: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0.0, le=1.0)
    duration_ms: int = Field(ge=0)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    provider_ref: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)


class TranscriptionFailure(BaseModel):
    """Typed, non-throwing provider failure suitable for the human fallback path."""

    model_config = ConfigDict(frozen=True)

    code: FailureCode
    provider: str
    model: str
    retryable: bool
    latency_ms: int = Field(ge=0)


TranscriptionResult: TypeAlias = Transcript | TranscriptionFailure


class TranscriptionProvider(Protocol):
    """Keep every speech provider behind the same byte-oriented async boundary."""

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str,
        hint_locale: str,
    ) -> TranscriptionResult: ...


def _normalize_mime_type(mime_type: str) -> str:
    return mime_type.strip().lower().split(";", 1)[0]


def _normalize_hint_locale(hint_locale: str) -> str:
    normalized = hint_locale.strip()
    if normalized in {"zh", "zh-CN", "cmn-Hans-CN"}:
        return "zh-CN"
    if normalized in {"en", "en-SG"}:
        return "en-SG"
    return normalized or "en-SG"


class StubTranscription:
    """Produce a stable transcript keyed only by audio bytes and the locale hint."""

    provider_name: Final = "stub"
    model_name: Final = "stub-transcription-v1"

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str,
        hint_locale: str,
    ) -> TranscriptionResult:
        started = time.monotonic()
        normalized_mime = _normalize_mime_type(mime_type)
        if not audio_bytes or normalized_mime not in SUPPORTED_AUDIO_MIME_TYPES:
            return TranscriptionFailure(
                code="invalid_audio",
                provider=self.provider_name,
                model=self.model_name,
                retryable=False,
                latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            )

        digest = sha256(audio_bytes).hexdigest()
        normalized_hint = _normalize_hint_locale(hint_locale)
        detected_locale = (
            "zh-CN" if normalized_hint == "zh-CN" else "en-SG"
        )
        text = (
            f"测试录音 {digest[:12]}"
            if detected_locale == "zh-CN"
            else f"Stub recording {digest[:12]}"
        )
        return Transcript(
            text=text,
            detected_locale=detected_locale,
            confidence=round(0.8 + int(digest[12:16], 16) / 0xFFFF * 0.19, 4),
            duration_ms=1000 + int(digest[28:36], 16) % 119_001,
            provider=self.provider_name,
            model=self.model_name,
            provider_ref=f"stub-asr-{digest[:24]}",
            latency_ms=int(digest[24:28], 16) % 25,
        )


class _GeminiPayload(BaseModel):
    text: str = Field(min_length=1)
    detected_locale: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0.0, le=1.0)
    duration_ms: int = Field(ge=0)


class _GenerateResponse(Protocol):
    @property
    def text(self) -> str | None: ...

    response_id: str | None
    model_version: str | None


class _AsyncModels(Protocol):
    async def generate_content(
        self,
        *,
        model: str,
        contents: object,
        config: object,
    ) -> _GenerateResponse: ...


class _AsyncClient(Protocol):
    models: _AsyncModels


class _VertexClient(Protocol):
    aio: _AsyncClient


@dataclass(frozen=True)
class GeminiTranscriptionConfig:
    project_id: str
    location: str
    model: str
    circuit_failure_threshold: int
    circuit_reset_seconds: float

    @classmethod
    def from_settings(cls, settings: Settings) -> GeminiTranscriptionConfig:
        return cls(
            project_id=settings.vertex_project_id.strip(),
            location=settings.vertex_location.strip(),
            model=settings.vertex_transcription_model.strip(),
            circuit_failure_threshold=settings.ai_circuit_failure_threshold,
            circuit_reset_seconds=settings.ai_circuit_reset_seconds,
        )

    @property
    def endpoint(self) -> str:
        return f"https://{self.location}-aiplatform.googleapis.com"

    def validate(self) -> None:
        if not self.project_id:
            raise ProviderConfigurationError("VERTEX_PROJECT_ID is required")
        if self.location != DEFAULT_VERTEX_LOCATION:
            raise ProviderConfigurationError(
                "VERTEX_LOCATION must be the configured Singapore region"
            )
        if not self.model:
            raise ProviderConfigurationError(
                "VERTEX_TRANSCRIPTION_MODEL is required"
            )


class _CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        reset_seconds: float,
        clock: _Clock,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._clock = clock
        self._failures = 0
        self._open_until = 0.0
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    async def allow_call(self) -> bool:
        async with self._lock:
            now = self._clock()
            if self._open_until == 0.0:
                return True
            if now < self._open_until or self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._open_until = 0.0
            self._probe_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._probe_in_flight = False
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._open_until = self._clock() + self._reset_seconds


def _make_vertex_client(config: GeminiTranscriptionConfig) -> _VertexClient:
    client = genai.Client(
        vertexai=True,
        project=config.project_id,
        location=config.location,
        http_options=types.HttpOptions(
            api_version="v1",
            timeout=int(REQUEST_TIMEOUT_SECONDS * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    return cast(_VertexClient, client)


def _prompt(hint_locale: str) -> str:
    return f"""You are a verbatim multilingual construction-site transcription engine.
Transcribe only the speech in the attached audio exactly as spoken.
Do not summarise, translate, paraphrase, correct grammar, or infer missing words.
Do not add punctuation that was not audibly spoken. Preserve Mandarin, English, and
code-switched trade terms in the language in which each word was spoken.
The user's UI locale is {hint_locale}. This is a weak recognition hint only: it must not
constrain language detection or override speech in another language. Return the detected
BCP-47 locale even when it disagrees with the hint; use "mul" for meaningful code-switching.
Return text, detected_locale, confidence from 0 to 1, and audio duration_ms."""


class GeminiTranscription:
    """Call Gemini only through Vertex AI's Singapore regional endpoint."""

    provider_name: Final = "vertex-gemini"

    def __init__(
        self,
        config: GeminiTranscriptionConfig,
        *,
        client: _VertexClient | None = None,
        sleep: _Sleep = asyncio.sleep,
        clock: _Clock = time.monotonic,
        random_source: _Random = random.random,
    ) -> None:
        config.validate()
        self.config = config
        self._client = client or _make_vertex_client(config)
        self._sleep = sleep
        self._clock = clock
        self._random = random_source
        self._circuit = _CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold,
            reset_seconds=config.circuit_reset_seconds,
            clock=clock,
        )

    def _failure(
        self,
        code: FailureCode,
        *,
        started: float,
        retryable: bool,
    ) -> TranscriptionFailure:
        return TranscriptionFailure(
            code=code,
            provider=self.provider_name,
            model=self.config.model,
            retryable=retryable,
            latency_ms=max(0, round((self._clock() - started) * 1000)),
        )

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str,
        hint_locale: str,
    ) -> TranscriptionResult:
        started = self._clock()
        normalized_mime = _normalize_mime_type(mime_type)
        if not audio_bytes or normalized_mime not in SUPPORTED_AUDIO_MIME_TYPES:
            return self._failure(
                "invalid_audio", started=started, retryable=False
            )
        if not await self._circuit.allow_call():
            return self._failure(
                "circuit_open", started=started, retryable=True
            )

        normalized_hint = _normalize_hint_locale(hint_locale)
        last_code: FailureCode = "provider_unavailable"
        for attempt in range(MAX_RETRIES + 1):
            attempt_code: FailureCode = "provider_unavailable"
            try:
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=_prompt(normalized_hint)),
                            types.Part.from_bytes(
                                data=audio_bytes,
                                mime_type=normalized_mime,
                            ),
                        ],
                    )
                ]
                async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                    response = await self._client.aio.models.generate_content(
                        model=self.config.model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            max_output_tokens=2048,
                            response_mime_type="application/json",
                            response_schema=_GeminiPayload,
                        ),
                    )
                raw = response.text
                if not isinstance(raw, str) or not raw.strip():
                    attempt_code = "invalid_response"
                    raise ValueError("Vertex returned an empty transcript")
                try:
                    payload = _GeminiPayload.model_validate_json(raw)
                except (ValidationError, ValueError) as error:
                    attempt_code = "invalid_response"
                    raise ValueError("Vertex returned an invalid transcript") from error
                await self._circuit.record_success()
                latency_ms = max(0, round((self._clock() - started) * 1000))
                provider_ref = (
                    response.response_id
                    or response.model_version
                    or f"sha256:{sha256(raw.encode()).hexdigest()[:24]}"
                )
                logger.info(
                    "transcription_provider_call",
                    extra={
                        "provider": self.provider_name,
                        "model": self.config.model,
                        "region": self.config.location,
                        "provider_ref": provider_ref,
                        "latency_ms": latency_ms,
                        "detected_locale": payload.detected_locale,
                    },
                )
                return Transcript(
                    **payload.model_dump(),
                    provider=self.provider_name,
                    model=self.config.model,
                    provider_ref=provider_ref,
                    latency_ms=latency_ms,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                last_code = attempt_code
                if attempt == MAX_RETRIES:
                    break
                delay = RETRY_BASE_SECONDS * (2**attempt) * (
                    0.5 + self._random()
                )
                logger.warning(
                    "transcription_provider_retry",
                    extra={
                        "provider": self.provider_name,
                        "model": self.config.model,
                        "region": self.config.location,
                        "attempt": attempt + 1,
                        "delay_seconds": round(delay, 4),
                        "error_type": type(error).__name__,
                    },
                )
                await self._sleep(delay)

        await self._circuit.record_failure()
        logger.error(
            "transcription_provider_unavailable",
            extra={
                "provider": self.provider_name,
                "model": self.config.model,
                "region": self.config.location,
                "attempts": MAX_RETRIES + 1,
                "failure_code": last_code,
            },
        )
        return self._failure(last_code, started=started, retryable=True)


@lru_cache(maxsize=4)
def _cached_gemini_provider(
    config: GeminiTranscriptionConfig,
) -> TranscriptionProvider:
    return GeminiTranscription(config)


def get_transcription_provider() -> TranscriptionProvider:
    """Use the stub in tests and only the configured Vertex implementation otherwise."""
    settings = get_settings()
    provider_name = settings.ai_provider.strip().lower()
    if provider_name == "stub":
        return StubTranscription()
    if provider_name in {"llm", "vertex"}:
        return _cached_gemini_provider(
            GeminiTranscriptionConfig.from_settings(settings)
        )
    raise ProviderConfigurationError(
        "configured AI_PROVIDER has no transcription implementation"
    )
