"""Test the public learning HTTP contract without a database or network."""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID

import asyncpg
from starlette.requests import Request
import pytest

from app.api import learning as learning_api
from app.api.learning import QuizAnswerRequest, learning_error
from app.domain.enums import ActorType
from app.services.learning_service import (
    LearningError,
    _public_briefing_dict,
    list_learning_briefings,
)
from app.services.report_service import Actor

BRIEFING_ID = UUID("71000000-0000-0000-0000-000000000001")
QUESTION_ID = UUID("72000000-0000-0000-0000-000000000001")
RESPONSE_ID = UUID("73000000-0000-0000-0000-000000000001")


def test_public_payload_never_exposes_the_answer_key() -> None:
    briefing = cast(
        asyncpg.Record,
        {
            "id": BRIEFING_ID,
            "version": 1,
            "body": {"en": "Lesson", "zh-CN": "课程"},
            "target_activity": None,
            "target_location": None,
            "valid_from": "2026-08-01T00:00:00Z",
            "valid_to": "2026-09-01T00:00:00Z",
            "approved_at": "2026-08-01T00:00:00Z",
        },
    )
    question = cast(
        asyncpg.Record,
        {
            "id": QUESTION_ID,
            "position": 1,
            "question": {"en": "Question", "zh-CN": "问题"},
            "explanation": {"en": "Why", "zh-CN": "原因"},
            "options": [
                {"en": "A", "zh-CN": "甲"},
                {"en": "B", "zh-CN": "乙"},
                {"en": "C", "zh-CN": "丙"},
                {"en": "D", "zh-CN": "丁"},
            ],
            "correct_option": 2,
        },
    )

    payload = _public_briefing_dict(briefing, [question])

    questions = payload["quiz_questions"]
    assert isinstance(questions, list)
    assert "correct_option" not in questions[0]


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("briefing_inactive", 404),
        ("quiz_question_not_found", 404),
        ("quiz_option_invalid", 422),
        ("quiz_rate_limited", 429),
    ],
)
def test_learning_errors_keep_machine_codes(code: str, expected_status: int) -> None:
    mapped = learning_error(LearningError(code, "developer detail"))
    assert mapped.status_code == expected_status
    assert mapped.detail == {"code": code, "message": "developer detail"}
    if code == "quiz_rate_limited":
        assert mapped.headers == {"Retry-After": "60"}


def test_public_quiz_endpoint_passes_anonymous_ip_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_submit(
        token: str,
        question_id: UUID,
        selected_option: int,
        *,
        actor: Actor | None,
        client_ip: str,
    ) -> dict[str, object]:
        captured.update(
            {
                "token": token,
                "question_id": question_id,
                "selected_option": selected_option,
                "actor": actor,
                "client_ip": client_ip,
            }
        )
        return {
            "response_id": RESPONSE_ID,
            "is_correct": True,
            "correct_option": 1,
        }

    monkeypatch.setattr(learning_api, "submit_quiz_answer", fake_submit)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/briefings/token/quiz",
            "headers": [],
            "client": ("203.0.113.7", 12345),
        }
    )
    result = asyncio.run(
        learning_api.post_quiz_answer(
            "token",
            QuizAnswerRequest(question_id=QUESTION_ID, selected_option=1),
            request,
            None,
        )
    )

    assert result == {
        "response_id": str(RESPONSE_ID),
        "is_correct": True,
        "correct_option": 1,
    }
    assert captured == {
        "token": "token",
        "question_id": QUESTION_ID,
        "selected_option": 1,
        "actor": None,
        "client_ip": "203.0.113.7",
    }


def test_machine_actor_cannot_open_signed_learning_feed() -> None:
    with pytest.raises(LearningError) as error:
        asyncio.run(
            list_learning_briefings(
                Actor(ActorType.SYSTEM, None, None)
            )
        )
    assert error.value.code == "learning_actor_forbidden"
