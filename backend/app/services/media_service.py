"""Validate private report media and mint short-lived read URLs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any, cast
from urllib.parse import quote, urljoin
from uuid import UUID

import asyncpg
import httpx

from app.config import Settings, get_settings
from app.db import connection
from app.domain.enums import ActorType, MediaPhase, Role
from app.services.report_service import Actor


class MediaError(Exception):
    """Carry a stable API code without turning developer text into UI copy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class MediaPolicy:
    """Keep media type, size, bucket, and expiry changes out of endpoint logic."""

    bucket: str
    allowed_mime_types: frozenset[str]
    max_bytes: int
    signed_url_ttl_seconds: int


MediaSigner = Callable[[str, MediaPolicy], Awaitable[str]]
MediaBatchSigner = Callable[[list[str], MediaPolicy], Awaitable[dict[str, str]]]


def media_policy(settings: Settings | None = None) -> MediaPolicy:
    """Build the media policy from configuration so Phase 7 can extend it safely."""
    configured = settings or get_settings()
    allowed = frozenset(
        value.strip().lower()
        for value in configured.report_media_allowed_mime_types.split(",")
        if value.strip()
    )
    return MediaPolicy(
        bucket=configured.report_media_bucket,
        allowed_mime_types=allowed,
        max_bytes=configured.report_media_max_bytes,
        signed_url_ttl_seconds=configured.report_media_signed_url_ttl_seconds,
    )


def validate_media_registration(
    *,
    report_id: UUID,
    reporter_id: UUID,
    actor: Actor,
    storage_path: str,
    requested_mime_type: str,
    object_mime_type: str,
    object_size: int,
    phase: MediaPhase,
    evidence_allowed: bool = False,
    policy: MediaPolicy | None = None,
) -> str:
    """Trust the stored object's metadata only after ownership and policy checks."""
    active_policy = policy or media_policy()
    if actor.actor_type is not ActorType.HUMAN or actor.profile_id is None:
        raise MediaError("media_actor_not_permitted", "media registration requires a human profile")

    parts = storage_path.split("/")
    if (
        len(parts) != 3
        or parts[0] != str(actor.profile_id)
        or parts[1] != str(report_id)
        or not parts[2]
        or parts[2] in {".", ".."}
        or "\\" in storage_path
    ):
        raise MediaError("media_path_invalid", "storage path does not belong to this actor and report")

    original_allowed = (
        phase is MediaPhase.ORIGINAL
        and actor.role is Role.REPORTER
        and reporter_id == actor.profile_id
    )
    responsible_evidence_allowed = (
        phase is MediaPhase.EVIDENCE
        and actor.role is Role.RESPONSIBLE
        and evidence_allowed
    )
    if not original_allowed and not responsible_evidence_allowed:
        raise MediaError(
            "media_phase_not_permitted",
            "actor cannot register media for this report phase",
        )

    requested = requested_mime_type.strip().lower()
    stored = object_mime_type.strip().lower()
    if requested not in active_policy.allowed_mime_types or stored not in active_policy.allowed_mime_types:
        raise MediaError("media_type_not_allowed", "stored object MIME type is not allowed")
    if requested != stored:
        raise MediaError("media_type_mismatch", "request MIME type does not match stored object metadata")
    if object_size <= 0:
        raise MediaError("media_object_invalid", "stored object size is missing or invalid")
    if object_size > active_policy.max_bytes:
        raise MediaError("media_too_large", "stored object exceeds the configured byte limit")
    return stored


def _storage_metadata(value: object) -> tuple[str, int]:
    if isinstance(value, str):
        try:
            metadata = cast(dict[str, object], json.loads(value))
        except (json.JSONDecodeError, TypeError) as error:
            raise MediaError("media_object_invalid", "stored object metadata is invalid") from error
    elif isinstance(value, dict):
        metadata = cast(dict[str, object], value)
    else:
        raise MediaError("media_object_invalid", "stored object metadata is missing")

    mime_value = metadata.get("mimetype", metadata.get("contentType", ""))
    size_value = metadata.get("size", metadata.get("contentLength", 0))
    try:
        object_size = int(cast(str | int, size_value))
    except (TypeError, ValueError) as error:
        raise MediaError("media_object_invalid", "stored object size is invalid") from error
    return str(mime_value), object_size


async def register_report_media(
    report_id: UUID,
    actor: Actor,
    *,
    storage_path: str,
    mime_type: str,
    phase: MediaPhase,
    caption: str | None,
) -> asyncpg.Record:
    """Register only an already-uploaded object whose database metadata is trustworthy."""
    policy = media_policy()
    async with connection() as conn:
        async with conn.transaction():
            report = await conn.fetchrow(
                """
                select
                  report.reporter_id,
                  exists (
                    select 1
                    from report_assignments assignment
                    join corrective_actions action
                      on action.assignment_id = assignment.id
                     and action.report_id = assignment.report_id
                    where assignment.report_id = report.id
                      and assignment.assignee_id = $2
                      and assignment.active
                      and action.status = 'assigned'::action_status
                      and report.status = 'action_assigned'::report_status
                  ) as evidence_allowed
                from reports report
                where report.id = $1
                for share
                """,
                report_id,
                actor.profile_id,
            )
            if report is None:
                raise MediaError("report_not_found", "report does not exist")

            try:
                stored_object = await conn.fetchrow(
                    """
                    SELECT metadata FROM storage.objects
                    WHERE bucket_id = $1 AND name = $2
                    """,
                    policy.bucket,
                    storage_path,
                )
            except asyncpg.UndefinedTableError as error:
                raise MediaError("storage_unavailable", "Supabase Storage schema is unavailable") from error
            if stored_object is None:
                raise MediaError("media_object_not_found", "uploaded storage object does not exist")
            object_mime_type, object_size = _storage_metadata(stored_object["metadata"])
            normalized_mime_type = validate_media_registration(
                report_id=report_id,
                reporter_id=report["reporter_id"],
                actor=actor,
                storage_path=storage_path,
                requested_mime_type=mime_type,
                object_mime_type=object_mime_type,
                object_size=object_size,
                phase=phase,
                evidence_allowed=report["evidence_allowed"],
                policy=policy,
            )
            try:
                media = await conn.fetchrow(
                    """
                    INSERT INTO report_media (report_id, storage_path, mime_type, phase, caption)
                    VALUES ($1, $2, $3, $4::media_phase, $5)
                    RETURNING *
                    """,
                    report_id,
                    storage_path,
                    normalized_mime_type,
                    phase.value,
                    caption,
                )
            except asyncpg.UniqueViolationError as error:
                raise MediaError("media_already_registered", "storage object is already registered") from error
    if media is None:
        raise RuntimeError("database did not return registered media")
    return media


def assert_report_readable(
    report: asyncpg.Record | Mapping[str, Any],
    actor: Actor,
) -> None:
    """Prevent signed bearer URLs from being minted for an unauthorised reader."""
    if actor.actor_type is not ActorType.HUMAN or actor.profile_id is None or actor.role is None:
        raise MediaError("report_forbidden", "report access requires a human profile")
    if actor.role in {Role.REVIEWER, Role.ADMIN}:
        return
    if actor.role is Role.REPORTER and report["reporter_id"] == actor.profile_id:
        return
    raise MediaError("report_forbidden", "actor cannot read this report")


async def create_signed_url(
    storage_path: str,
    policy: MediaPolicy,
    *,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Use the server-only service key to mint one time-bounded Storage URL."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise MediaError("storage_not_configured", "Supabase Storage signing configuration is missing")

    storage_base = f"{settings.supabase_url.rstrip('/')}/storage/v1"
    endpoint = (
        f"{storage_base}/object/sign/{quote(policy.bucket, safe='')}"
        f"/{quote(storage_path, safe='/')}"
    )
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await active_client.post(
            endpoint,
            headers=headers,
            json={"expiresIn": policy.signed_url_ttl_seconds},
        )
    except httpx.HTTPError as error:
        raise MediaError("storage_sign_failed", "Storage signing request failed") from error
    finally:
        if owns_client:
            await active_client.aclose()
    if response.status_code >= 400:
        raise MediaError("storage_sign_failed", "Storage rejected the signing request")
    body = cast(dict[str, object], response.json())
    signed_path = body.get("signedURL", body.get("signedUrl"))
    if not isinstance(signed_path, str) or not signed_path:
        raise MediaError("storage_sign_failed", "Storage signing response has no URL")
    if signed_path.startswith(("http://", "https://")):
        return signed_path
    return urljoin(f"{storage_base}/", signed_path.lstrip("/"))


async def create_signed_urls(
    storage_paths: list[str],
    policy: MediaPolicy,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, str]:
    """Mint a page of thumbnail URLs with one Storage request."""
    if not storage_paths:
        return {}
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise MediaError("storage_not_configured", "Supabase Storage signing configuration is missing")

    storage_base = f"{settings.supabase_url.rstrip('/')}/storage/v1"
    endpoint = f"{storage_base}/object/sign/{quote(policy.bucket, safe='')}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await active_client.post(
            endpoint,
            headers=headers,
            json={"expiresIn": policy.signed_url_ttl_seconds, "paths": storage_paths},
        )
    except httpx.HTTPError as error:
        raise MediaError("storage_sign_failed", "Storage signing request failed") from error
    finally:
        if owns_client:
            await active_client.aclose()
    if response.status_code >= 400:
        raise MediaError("storage_sign_failed", "Storage rejected the signing request")

    body = response.json()
    if not isinstance(body, list):
        raise MediaError("storage_sign_failed", "Storage signing response is invalid")
    signed_urls: dict[str, str] = {}
    for item in body:
        if not isinstance(item, dict):
            raise MediaError("storage_sign_failed", "Storage signing response is invalid")
        storage_path = item.get("path")
        signed_path = item.get("signedURL", item.get("signedUrl"))
        if not isinstance(storage_path, str) or not isinstance(signed_path, str) or not signed_path:
            raise MediaError("storage_sign_failed", "Storage signing response has no URL")
        signed_urls[storage_path] = (
            signed_path
            if signed_path.startswith(("http://", "https://"))
            else urljoin(f"{storage_base}/", signed_path.lstrip("/"))
        )
    if set(signed_urls) != set(storage_paths):
        raise MediaError("storage_sign_failed", "Storage did not sign every requested object")
    return signed_urls


async def get_signed_media_urls(
    storage_paths: list[str],
    *,
    signer: MediaBatchSigner | None = None,
) -> tuple[dict[str, str], datetime]:
    """Batch-sign unique paths and return their shared expiration time."""
    policy = media_policy()
    unique_paths = list(dict.fromkeys(storage_paths))
    active_signer = signer or create_signed_urls
    signed_urls = await active_signer(unique_paths, policy)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=policy.signed_url_ttl_seconds)
    return signed_urls, expires_at


async def get_signed_report_media(
    report_id: UUID,
    *,
    signer: MediaSigner | None = None,
) -> list[dict[str, object]]:
    """Return private media with URLs that expire together after the configured TTL."""
    policy = media_policy()
    async with connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, storage_path, mime_type, phase::text, caption,
                   corrective_action_id, created_at
            FROM report_media WHERE report_id = $1 ORDER BY created_at, id
            """,
            report_id,
        )
    if not rows:
        return []

    active_signer = signer or create_signed_url
    signed_urls = await asyncio.gather(
        *(active_signer(row["storage_path"], policy) for row in rows)
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=policy.signed_url_ttl_seconds)
    return [
        {
            **dict(row),
            "signed_url": signed_url,
            "signed_url_expires_at": expires_at,
        }
        for row, signed_url in zip(rows, signed_urls, strict=True)
    ]
