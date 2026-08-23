"""Test briefing permissions, token entropy, and machine-coded API errors offline."""

from __future__ import annotations

import asyncio
import base64
from uuid import UUID

import pytest

from app.api.briefings import briefing_error
from app.domain.enums import ActorType, Role
from app.services.briefing_service import (
    BriefingError,
    QR_TOKEN_BYTES,
    _new_qr_token,
    list_managed_briefings,
)
from app.services.report_service import Actor

REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")


def test_only_a_reviewer_can_open_briefing_management() -> None:
    with pytest.raises(BriefingError) as error:
        asyncio.run(
            list_managed_briefings(
                Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER)
            )
        )
    assert error.value.code == "briefing_actor_forbidden"
    assert briefing_error(error.value).status_code == 403


def test_qr_token_carries_more_than_128_bits() -> None:
    token = _new_qr_token()
    padding = "=" * (-len(token) % 4)
    assert len(base64.urlsafe_b64decode(token + padding)) == QR_TOKEN_BYTES
    assert QR_TOKEN_BYTES * 8 >= 128


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("briefing_not_found", 404),
        ("briefing_not_draft", 409),
        ("briefing_both_locales_required", 422),
    ],
)
def test_briefing_errors_keep_the_uniform_machine_contract(
    code: str,
    expected_status: int,
) -> None:
    mapped = briefing_error(BriefingError(code, "developer detail"))
    assert mapped.status_code == expected_status
    assert mapped.detail == {"code": code, "message": "developer detail"}
