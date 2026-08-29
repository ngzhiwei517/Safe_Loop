"""Test report-media ownership, policy configuration, and URL expiry."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

import httpx
import pytest

from app.api import reports as reports_api
from app.api.reports import media_error
from app.config import get_settings
from app.domain.enums import ActorType, MediaPhase, Role
from app.services.media_service import (
    MediaError,
    MediaPolicy,
    audio_media_policy,
    assert_report_readable,
    create_signed_url,
    create_signed_urls,
    media_policy_for_mime_type,
    validate_media_registration,
)
from app.services.report_service import Actor

REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("00000000-0000-0000-0000-000000000002")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
IMAGE_POLICY = MediaPolicy(
    bucket="report-media",
    allowed_mime_types=frozenset({"image/jpeg", "image/png", "image/webp"}),
    max_bytes=10 * 1024 * 1024,
    signed_url_ttl_seconds=600,
)
AUDIO_POLICY = MediaPolicy(
    bucket="report-audio",
    allowed_mime_types=frozenset({"audio/webm", "audio/mp4", "audio/mpeg"}),
    max_bytes=25 * 1024 * 1024,
    signed_url_ttl_seconds=600,
)


def validate(
    *,
    storage_path: str | None = None,
    requested_mime_type: str = "image/jpeg",
    object_mime_type: str = "image/jpeg",
    object_size: int = 1024,
    policy: MediaPolicy = IMAGE_POLICY,
) -> str:
    return validate_media_registration(
        report_id=REPORT_ID,
        reporter_id=REPORTER_ID,
        actor=Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        storage_path=storage_path or f"{REPORTER_ID}/{REPORT_ID}/photo.jpg",
        requested_mime_type=requested_mime_type,
        object_mime_type=object_mime_type,
        object_size=object_size,
        phase=MediaPhase.ORIGINAL,
        policy=policy,
    )


@pytest.mark.parametrize("mime_type", ["image/jpeg", "image/png", "image/webp"])
def test_allowed_image_types_are_accepted(mime_type: str) -> None:
    assert validate(requested_mime_type=mime_type, object_mime_type=mime_type) == mime_type


def test_path_must_belong_to_actor_and_report() -> None:
    with pytest.raises(MediaError) as error:
        validate(storage_path=f"{OTHER_ID}/{REPORT_ID}/photo.jpg")
    assert error.value.code == "media_path_invalid"


def test_reporter_cannot_register_future_evidence_phase() -> None:
    with pytest.raises(MediaError) as error:
        validate_media_registration(
            report_id=REPORT_ID,
            reporter_id=REPORTER_ID,
            actor=Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
            storage_path=f"{REPORTER_ID}/{REPORT_ID}/photo.jpg",
            requested_mime_type="image/jpeg",
            object_mime_type="image/jpeg",
            object_size=1024,
            phase=MediaPhase.EVIDENCE,
            policy=IMAGE_POLICY,
        )
    assert error.value.code == "media_phase_not_permitted"


def test_active_responsible_actor_can_register_evidence_phase() -> None:
    assert (
        validate_media_registration(
            report_id=REPORT_ID,
            reporter_id=REPORTER_ID,
            actor=Actor(ActorType.HUMAN, OTHER_ID, Role.RESPONSIBLE),
            storage_path=f"{OTHER_ID}/{REPORT_ID}/proof.jpg",
            requested_mime_type="image/jpeg",
            object_mime_type="image/jpeg",
            object_size=1024,
            phase=MediaPhase.EVIDENCE,
            evidence_allowed=True,
            policy=IMAGE_POLICY,
        )
        == "image/jpeg"
    )


def test_stored_metadata_not_browser_claim_controls_mime_type() -> None:
    with pytest.raises(MediaError) as error:
        validate(requested_mime_type="image/jpeg", object_mime_type="image/png")
    assert error.value.code == "media_type_mismatch"


def test_media_over_ten_megabytes_is_rejected() -> None:
    with pytest.raises(MediaError) as error:
        validate(object_size=IMAGE_POLICY.max_bytes + 1)
    assert error.value.code == "media_too_large"
    assert media_error(error.value).status_code == 413


@pytest.mark.parametrize("mime_type", ["audio/webm", "audio/mp4", "audio/mpeg"])
def test_allowed_audio_types_are_accepted(mime_type: str) -> None:
    assert validate(
        requested_mime_type=mime_type,
        object_mime_type=mime_type,
        object_size=20 * 1024 * 1024,
        policy=AUDIO_POLICY,
    ) == mime_type


def test_audio_policy_uses_private_audio_bucket_and_25mb_cap() -> None:
    policy = audio_media_policy()
    assert policy.bucket == "report-audio"
    assert policy.max_bytes == 25 * 1024 * 1024
    assert media_policy_for_mime_type("audio/webm;codecs=opus") == policy


def test_audio_over_twenty_five_megabytes_is_rejected() -> None:
    with pytest.raises(MediaError) as error:
        validate(
            requested_mime_type="audio/webm",
            object_mime_type="audio/webm",
            object_size=AUDIO_POLICY.max_bytes + 1,
            policy=AUDIO_POLICY,
        )
    assert error.value.code == "media_too_large"


def test_only_owner_reviewer_or_admin_can_receive_signed_media() -> None:
    report = {"reporter_id": REPORTER_ID}
    assert_report_readable(report, Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER))
    assert_report_readable(report, Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER))
    with pytest.raises(MediaError) as error:
        assert_report_readable(report, Actor(ActorType.HUMAN, OTHER_ID, Role.REPORTER))
    assert error.value.code == "report_forbidden"


def test_storage_signing_uses_ten_minute_expiry_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-test-key")
    get_settings.cache_clear()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"signedURL": "/object/sign/report-media/path/photo.jpg?token=test"},
        )

    async def exercise() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await create_signed_url("path/photo.jpg", IMAGE_POLICY, client=client)

    try:
        url = asyncio.run(exercise())
    finally:
        get_settings.cache_clear()

    assert url == "https://project.example/storage/v1/object/sign/report-media/path/photo.jpg?token=test"
    assert len(requests) == 1
    assert json.loads(requests[0].content) == {"expiresIn": 600}
    assert requests[0].headers["authorization"] == "Bearer service-test-key"


def test_thumbnail_page_uses_one_batch_signing_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-test-key")
    get_settings.cache_clear()
    requests: list[httpx.Request] = []
    paths = ["path/photo-a.jpg", "path/photo-b.jpg"]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "path": path,
                    "signedURL": f"/object/sign/report-media/{path}?token=test",
                }
                for path in paths
            ],
        )

    async def exercise() -> dict[str, str]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await create_signed_urls(paths, IMAGE_POLICY, client=client)

    try:
        urls = asyncio.run(exercise())
    finally:
        get_settings.cache_clear()

    assert len(requests) == 1
    assert requests[0].url.path.endswith("/object/sign/report-media")
    assert json.loads(requests[0].content) == {"expiresIn": 600, "paths": paths}
    assert urls[paths[0]].endswith("photo-a.jpg?token=test")


def test_reviewer_report_read_includes_signed_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_report(_: UUID) -> dict[str, object]:
        return {
            "id": REPORT_ID,
            "reporter_id": REPORTER_ID,
            "status": "submitted",
        }

    async def fake_media(_: UUID) -> list[dict[str, object]]:
        return [
            {
                "id": "media-id",
                "signed_url": "https://project.example/storage/photo.jpg?token=signed",
                "signed_url_expires_at": "2026-08-22T09:10:00Z",
            }
        ]

    async def fake_clarifications(_: UUID) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(reports_api, "get_report", fake_report)
    monkeypatch.setattr(reports_api, "get_signed_report_media", fake_media)
    monkeypatch.setattr(
        reports_api,
        "list_report_clarifications",
        fake_clarifications,
    )
    result = asyncio.run(
        reports_api.report_detail(
            REPORT_ID,
            Actor(ActorType.HUMAN, REVIEWER_ID, Role.REVIEWER),
        )
    )

    media = result["media"]
    assert isinstance(media, list)
    assert media[0]["signed_url"].endswith("token=signed")
