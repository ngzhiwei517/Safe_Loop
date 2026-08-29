"""Configure Gemini 3.5 Transcribe Live without exposing Google credentials."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
import time
from typing import Final
import wave

from google import genai
from google.genai import types

from app.config import Settings
from app.ai.transcription import Transcript, TranscriptionFailure, TranscriptionResult

LIVE_AUDIO_MIME_TYPE: Final = "audio/pcm;rate=16000"
ENGLISH_CONSTRUCTION_VOCABULARY: Final = [
    "guardrail",
    "formwork",
    "scaffold",
    "toe board",
    "permit-to-work",
]
MANDARIN_CONSTRUCTION_VOCABULARY: Final = [
    "配电箱",
    "安全带",
    "动火作业",
]


def detected_locale_or_infer(provider_locale: str | None, text: str) -> str:
    if provider_locale:
        return provider_locale
    has_han = any("\u3400" <= character <= "\u9fff" for character in text)
    has_latin = any(character.isascii() and character.isalpha() for character in text)
    if has_han and has_latin:
        return "mul"
    if has_han:
        return "cmn-Hans-CN"
    if has_latin:
        return "en"
    return "und"


@dataclass(frozen=True)
class LiveTranscriptionConfig:
    project_id: str
    location: str
    model: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "LiveTranscriptionConfig":
        return cls(
            project_id=settings.vertex_project_id.strip(),
            location=settings.vertex_live_transcription_location.strip(),
            model=settings.vertex_live_transcription_model.strip(),
        )

    def validate(self) -> None:
        if not self.project_id:
            raise ValueError("VERTEX_PROJECT_ID is required")
        if self.location != "global":
            raise ValueError("Gemini 3.5 Transcribe Live currently requires global")
        if self.model != "gemini-3.5-transcribe-live-preview":
            raise ValueError("unsupported live transcription model")


def make_live_client(config: LiveTranscriptionConfig) -> genai.Client:
    config.validate()
    return genai.Client(
        enterprise=True,
        project=config.project_id,
        location=config.location,
        http_options=types.HttpOptions(api_version="v1"),
    )


def live_connect_config(hint_locale: str) -> types.LiveConnectConfig:
    # The August 2026 preview currently rejects its documented language_auto
    # field and requires language_codes. Supply both product languages on every
    # session so the UI locale never prevents Mandarin/English code-switching;
    # hint_locale remains part of SafeLoop's immutable audit record.
    vocabulary = (
        MANDARIN_CONSTRUCTION_VOCABULARY
        if hint_locale in {"zh-CN", "cmn-Hans-CN"}
        else ENGLISH_CONSTRUCTION_VOCABULARY
    )
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.TEXT],
        input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=["cmn-Hans-CN", "en-GB"],
            custom_vocabulary=vocabulary,
        ),
    )


class GeminiLiveFileTranscription:
    """Feed committed 16 kHz WAV fixtures through Live for manual A/B evaluation."""

    def __init__(self, config: LiveTranscriptionConfig) -> None:
        config.validate()
        self.config = config

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str,
        hint_locale: str,
    ) -> TranscriptionResult:
        started = time.monotonic()
        try:
            with wave.open(BytesIO(audio_bytes), "rb") as source:
                if (
                    source.getnchannels() != 1
                    or source.getsampwidth() != 2
                    or source.getframerate() != 16000
                ):
                    raise ValueError("live eval requires mono 16-bit 16 kHz PCM")
                frames = source.getnframes()
                pcm = source.readframes(frames)
        except (EOFError, ValueError, wave.Error):
            return TranscriptionFailure(
                code="invalid_audio",
                provider="vertex-gemini-live",
                model=self.config.model,
                retryable=False,
                latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            )
        if mime_type.split(";", 1)[0].strip().lower() != "audio/wav":
            return TranscriptionFailure(
                code="invalid_audio",
                provider="vertex-gemini-live",
                model=self.config.model,
                retryable=False,
                latency_ms=0,
            )

        final_parts: list[str] = []
        detected_locale = "und"
        try:
            client = make_live_client(self.config)
            async with client.aio.live.connect(
                model=self.config.model,
                config=live_connect_config(hint_locale),
            ) as session:
                for offset in range(0, len(pcm), 6400):
                    chunk = pcm[offset : offset + 6400]
                    await session.send_realtime_input(
                        audio={"data": chunk, "mime_type": LIVE_AUDIO_MIME_TYPE}
                    )
                    await asyncio.sleep(len(chunk) / 32000)
                await session.send_realtime_input(audio_stream_end=True)

                async def collect() -> None:
                    nonlocal detected_locale
                    receiver = session.receive().__aiter__()
                    while True:
                        try:
                            message = await asyncio.wait_for(
                                receiver.__anext__(),
                                timeout=2.0 if final_parts else 10.0,
                            )
                        except (StopAsyncIteration, TimeoutError):
                            return
                        content = message.server_content
                        final = content.input_transcription if content else None
                        if final is not None and final.text:
                            if not final_parts or final_parts[-1] != final.text:
                                final_parts.append(final.text)
                            detected_locale = detected_locale_or_infer(
                                final.language_code,
                                " ".join(final_parts),
                            )
                await collect()
                provider_ref = session.session_id or "live-session"
        except Exception:
            return TranscriptionFailure(
                code="provider_unavailable",
                provider="vertex-gemini-live",
                model=self.config.model,
                retryable=True,
                latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            )
        text = " ".join(part.strip() for part in final_parts if part.strip()).strip()
        if not text:
            return TranscriptionFailure(
                code="invalid_response",
                provider="vertex-gemini-live",
                model=self.config.model,
                retryable=True,
                latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            )
        return Transcript(
            text=text,
            detected_locale=detected_locale,
            confidence=None,
            duration_ms=round(frames / 16000 * 1000),
            provider="vertex-gemini-live",
            model=self.config.model,
            provider_ref=provider_ref,
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
        )
