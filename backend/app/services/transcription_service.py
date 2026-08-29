"""Load authorised private audio and append its transcription audit row."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, cast
from urllib.parse import quote
from uuid import UUID

import asyncpg
import httpx

from app.ai.transcription import (
    SUPPORTED_AUDIO_MIME_TYPES,
    Transcript,
    TranscriptionFailure,
)
from app.config import get_settings
from app.db import connection
from app.domain.enums import MediaPhase, Role
from app.services.media_service import MediaError, assert_report_readable
from app.services.report_service import Actor


class TranscriptionServiceError(Exception):
    """Carry a stable error code from storage/database work to the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AudioMedia:
    id: UUID
    report_id: UUID
    storage_path: str
    mime_type: str


async def get_audio_media(media_id: UUID, actor: Actor) -> AudioMedia:
    """Resolve one registered audio object only when the caller can read its report."""
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            select media.id, media.report_id, media.storage_path, media.mime_type,
                   media.phase::text, report.reporter_id,
                   exists (
                     select 1 from report_assignments as assignment
                     where assignment.report_id = media.report_id
                       and assignment.assignee_id = $2
                       and assignment.active
                   ) as responsible_assigned
            from report_media as media
            join reports as report on report.id = media.report_id
            where media.id = $1
            """,
            media_id,
            actor.profile_id,
        )
    if row is None:
        raise TranscriptionServiceError(
            "transcription_media_not_found", "audio media does not exist"
        )
    try:
        assert_report_readable(
            cast(asyncpg.Record | Mapping[str, Any], row),
            actor,
        )
    except MediaError as error:
        responsible_upload = (
            actor.profile_id is not None
            and actor.role is Role.RESPONSIBLE
            and row["phase"] == MediaPhase.EVIDENCE.value
            and row["responsible_assigned"]
            and str(row["storage_path"]).startswith(f"{actor.profile_id}/")
        )
        if not responsible_upload:
            raise TranscriptionServiceError(
                "transcription_forbidden", "actor cannot transcribe this media"
            ) from error

    mime_type = str(row["mime_type"]).strip().lower().split(";", 1)[0]
    if mime_type not in SUPPORTED_AUDIO_MIME_TYPES:
        raise TranscriptionServiceError(
            "transcription_media_type_invalid",
            "registered media is not supported audio",
        )
    return AudioMedia(
        id=row["id"],
        report_id=row["report_id"],
        storage_path=row["storage_path"],
        mime_type=mime_type,
    )


async def download_audio(
    media: AudioMedia,
    *,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    """Download private audio with the server-only service credential."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise TranscriptionServiceError(
            "transcription_storage_not_configured",
            "Supabase Storage download configuration is missing",
        )
    endpoint = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{quote(settings.report_audio_bucket, safe='')}/"
        f"{quote(media.storage_path, safe='/')}"
    )
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=15.0)
    try:
        response = await active_client.get(endpoint, headers=headers)
    except httpx.HTTPError as error:
        raise TranscriptionServiceError(
            "transcription_storage_failed", "audio download failed"
        ) from error
    finally:
        if owns_client:
            await active_client.aclose()
    if response.status_code == 404:
        raise TranscriptionServiceError(
            "transcription_media_not_found", "audio object does not exist"
        )
    if response.status_code >= 400:
        raise TranscriptionServiceError(
            "transcription_storage_failed", "storage rejected the audio download"
        )
    audio_bytes = response.content
    if not audio_bytes:
        raise TranscriptionServiceError(
            "transcription_audio_empty", "audio object is empty"
        )
    if len(audio_bytes) > settings.report_audio_max_bytes:
        raise TranscriptionServiceError(
            "transcription_audio_too_large",
            "audio object exceeds the configured byte limit",
        )
    return audio_bytes


async def persist_transcript(
    media_id: UUID,
    *,
    report_id: UUID,
    hint_locale: str,
    transcript: Transcript,
) -> asyncpg.Record:
    """Append one immutable raw transcript without touching its report."""
    async with connection() as conn:
        row = await conn.fetchrow(
            """
            insert into transcripts (
              media_id, report_id, provider, model, hint_locale, detected_locale,
              text_raw, confidence, duration_ms, provider_ref, latency_ms
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            returning *
            """,
            media_id,
            report_id,
            transcript.provider,
            transcript.model,
            hint_locale,
            transcript.detected_locale,
            transcript.text,
            transcript.confidence,
            transcript.duration_ms,
            transcript.provider_ref,
            transcript.latency_ms,
        )
    if row is None:
        raise RuntimeError("database did not return the persisted transcript")
    return row


async def persist_transcription_attempt(
    media: AudioMedia,
    *,
    hint_locale: str,
    result: Transcript | TranscriptionFailure,
    transcript_id: UUID | None,
    usable: bool,
) -> None:
    """Append operational ASR telemetry without changing the request outcome."""
    transcript = result if isinstance(result, Transcript) else None
    failure = result if isinstance(result, TranscriptionFailure) else None
    async with connection() as conn:
        await conn.execute(
            """
            insert into transcription_attempts (
              media_id, report_id, transcript_id, provider, model,
              hint_locale, detected_locale, confidence, usable,
              failure_code, latency_ms
            ) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            media.id,
            media.report_id,
            transcript_id,
            result.provider,
            result.model,
            hint_locale,
            transcript.detected_locale if transcript is not None else None,
            transcript.confidence if transcript is not None else None,
            usable,
            failure.code if failure is not None else (
                "confidence_below_threshold" if not usable else None
            ),
            result.latency_ms,
        )
