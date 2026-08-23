"""Deliver active crew lessons and record bounded public quiz responses."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import cast
from uuid import UUID

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from app.config import get_settings
from app.db import connection
from app.domain.enums import ActorType
from app.services.report_service import Actor


class LearningError(Exception):
    """Carry a stable learning code to the HTTP boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _decoded_json(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def _human_id(actor: Actor) -> UUID:
    if actor.actor_type is not ActorType.HUMAN or actor.profile_id is None:
        raise LearningError("learning_actor_forbidden", "a human profile is required")
    return actor.profile_id


def _question_dict(row: asyncpg.Record, *, include_answer: bool) -> dict[str, object]:
    result: dict[str, object] = {
        "id": row["id"],
        "position": row["position"],
        "question": _decoded_json(row["question"]),
        "explanation": _decoded_json(row["explanation"]),
        "options": _decoded_json(row["options"]),
    }
    if include_answer:
        result["correct_option"] = row["correct_option"]
    return result


def _public_briefing_dict(
    row: asyncpg.Record,
    questions: list[asyncpg.Record],
) -> dict[str, object]:
    return {
        "id": row["id"],
        "version": row["version"],
        "body": _decoded_json(row["body"]),
        "target_activity": row["target_activity"],
        "target_location": row["target_location"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "approved_at": row["approved_at"],
        "quiz_questions": [
            _question_dict(question, include_answer=False) for question in questions
        ],
    }


async def _active_briefing(
    conn: PoolConnectionProxy[asyncpg.Record],
    token: str,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        select id, version, body, target_activity, target_location,
               valid_from, valid_to, approved_at
        from briefings
        where qr_token = $1
          and status = 'published'::briefing_status
          and valid_from <= now()
          and valid_to > now()
        """,
        token,
    )
    if row is None:
        raise LearningError("briefing_inactive", "briefing token is not active")
    return row


async def get_public_briefing(token: str) -> dict[str, object]:
    """Return one currently active published lesson without revealing quiz answers."""
    clean_token = token.strip()
    if not clean_token:
        raise LearningError("briefing_inactive", "briefing token is not active")
    async with connection() as conn:
        row = await _active_briefing(conn, clean_token)
        questions = await conn.fetch(
            """
            select id, position, question, explanation, options, correct_option
            from quiz_questions
            where briefing_id = $1
            order by position
            """,
            row["id"],
        )
    return _public_briefing_dict(row, list(questions))


async def _consume_rate_limit(client_ip: str) -> None:
    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
    window = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    limit = get_settings().quiz_rate_limit_per_minute
    async with connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "delete from quiz_rate_limits where window_started_at < now() - interval '2 hours'"
            )
            count = await conn.fetchval(
                """
                insert into quiz_rate_limits (ip_hash, window_started_at, request_count)
                values ($1, $2, 1)
                on conflict (ip_hash, window_started_at) do update
                  set request_count = quiz_rate_limits.request_count + 1
                  where quiz_rate_limits.request_count < $3
                returning request_count
                """,
                ip_hash,
                window,
                limit,
            )
    if count is None:
        raise LearningError("quiz_rate_limited", "quiz request rate limit exceeded")


async def submit_quiz_answer(
    token: str,
    question_id: UUID,
    selected_option: int,
    *,
    actor: Actor | None,
    client_ip: str,
) -> dict[str, object]:
    """Check one answer on the server and retain anonymous participation when needed."""
    if not 0 <= selected_option < 4:
        raise LearningError("quiz_option_invalid", "selected quiz option is invalid")
    await _consume_rate_limit(client_ip)
    respondent_id = None if actor is None else _human_id(actor)
    async with connection() as conn:
        async with conn.transaction():
            briefing = await _active_briefing(conn, token.strip())
            question = await conn.fetchrow(
                """
                select id, correct_option
                from quiz_questions
                where id = $1 and briefing_id = $2
                """,
                question_id,
                briefing["id"],
            )
            if question is None:
                raise LearningError(
                    "quiz_question_not_found",
                    "quiz question does not belong to the active briefing",
                )
            correct_option = int(question["correct_option"])
            is_correct = selected_option == correct_option
            response_id = await conn.fetchval(
                """
                insert into quiz_responses (
                  question_id, respondent_id, selected_option, is_correct
                )
                values ($1, $2, $3, $4)
                returning id
                """,
                question_id,
                respondent_id,
                selected_option,
                is_correct,
            )
    if not isinstance(response_id, UUID):
        raise RuntimeError("database did not return quiz response")
    return {
        "response_id": response_id,
        "is_correct": is_correct,
        "correct_option": correct_option,
    }


async def list_learning_briefings(actor: Actor) -> list[dict[str, object]]:
    """Rank active published lessons for a signed-in worker's known work context."""
    profile_id = _human_id(actor)
    async with connection() as conn:
        rows = await conn.fetch(
            """
            with viewer_context as (
              select lower(btrim(report.activity)) as activity,
                     lower(btrim(report.location_text)) as location
              from reports report
              where report.reporter_id = $1
                and report.created_at >= now() - interval '180 days'
              union
              select lower(btrim(report.activity)) as activity,
                     lower(btrim(report.location_text)) as location
              from report_assignments assignment
              join reports report on report.id = assignment.report_id
              where assignment.assignee_id = $1 and assignment.active
            ),
            active_versions as (
              select briefing.*,
                     row_number() over (
                       partition by briefing.report_id
                       order by briefing.version desc, briefing.id desc
                     ) as version_rank
              from briefings briefing
              where briefing.status = 'published'::briefing_status
                and briefing.valid_from <= now()
                and briefing.valid_to > now()
            )
            select
              briefing.id,
              briefing.version,
              briefing.body,
              briefing.target_activity,
              briefing.target_location,
              briefing.valid_from,
              briefing.valid_to,
              briefing.approved_at,
              briefing.qr_token,
              (
                (briefing.target_activity is not null and exists (
                  select 1 from viewer_context context
                  where context.activity = lower(btrim(briefing.target_activity))
                ))
                or
                (briefing.target_location is not null and exists (
                  select 1 from viewer_context context
                  where context.location = lower(btrim(briefing.target_location))
                ))
              ) as target_match,
              (select count(*)::integer from quiz_questions question
               where question.briefing_id = briefing.id) as question_count,
              (select count(distinct response.question_id)::integer
               from quiz_responses response
               join quiz_questions question on question.id = response.question_id
               where question.briefing_id = briefing.id
                 and response.respondent_id = $1) as answered_count
            from active_versions briefing
            where briefing.version_rank = 1
            order by target_match desc, briefing.approved_at desc, briefing.id desc
            """,
            profile_id,
        )
    result: list[dict[str, object]] = []
    for row in rows:
        question_count = int(row["question_count"])
        answered_count = int(row["answered_count"])
        item = dict(row)
        item["body"] = _decoded_json(item["body"])
        item["quiz_answered"] = question_count > 0 and answered_count >= question_count
        result.append(cast(dict[str, object], item))
    return result
