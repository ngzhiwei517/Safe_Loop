"""Own reviewer edits and publication without rewriting a published lesson."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import secrets
from typing import cast
from uuid import UUID

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from app.ai.lesson_graph import MAX_BRIEFING_EN_WORDS, MAX_BRIEFING_ZH_CHARACTERS
from app.db import connection
from app.domain.enums import (
    ActorType,
    BriefingStatus,
    ReportStatus,
    Role,
    SUPPORTED_LOCALES,
)
from app.domain.transitions import allowed_targets, find
from app.services.report_service import Actor, transition_report

EN_LOCALE, ZH_CN_LOCALE = SUPPORTED_LOCALES
QUIZ_QUESTION_COUNT = 3
QUIZ_OPTION_COUNT = 4
QR_TOKEN_BYTES = 32


class BriefingError(Exception):
    """Carry a stable briefing code to the HTTP boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class QuizEdit:
    """Carry one complete bilingual quiz question from the reviewer."""

    position: int
    question: dict[str, str]
    explanation: dict[str, str]
    options: list[dict[str, str]]
    correct_option: int


@dataclass(frozen=True)
class BriefingEdit:
    """Carry all editable fields as one versioned save operation."""

    body: dict[str, str]
    questions: list[QuizEdit]
    target_activity: str | None = None
    target_location: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


def _reviewer_id(actor: Actor) -> UUID:
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.role is not Role.REVIEWER
        or actor.profile_id is None
    ):
        raise BriefingError(
            "briefing_actor_forbidden",
            "briefing management requires a reviewer",
        )
    return actor.profile_id


def _decoded_json(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def _locale_map(
    value: dict[str, str],
    *,
    require_both: bool,
    code: str,
) -> dict[str, str]:
    if any(locale not in SUPPORTED_LOCALES for locale in value):
        raise BriefingError("briefing_locale_invalid", "briefing locale map is invalid")
    english = value.get(EN_LOCALE, "").strip()
    chinese = value.get(ZH_CN_LOCALE, "").strip()
    if not english:
        raise BriefingError(code, "English briefing content is required")
    if require_both and not chinese:
        raise BriefingError(
            "briefing_both_locales_required",
            "both briefing locales are required for publication",
        )
    return {EN_LOCALE: english, ZH_CN_LOCALE: chinese}


def _clean_questions(
    questions: list[QuizEdit],
    *,
    require_both: bool,
) -> list[QuizEdit]:
    if len(questions) != QUIZ_QUESTION_COUNT:
        raise BriefingError(
            "briefing_quiz_invalid",
            "a briefing requires exactly three quiz questions",
        )
    expected_positions = list(range(1, QUIZ_QUESTION_COUNT + 1))
    if sorted(question.position for question in questions) != expected_positions:
        raise BriefingError("briefing_quiz_invalid", "quiz positions are invalid")

    cleaned: list[QuizEdit] = []
    for item in sorted(questions, key=lambda question: question.position):
        if len(item.options) != QUIZ_OPTION_COUNT:
            raise BriefingError(
                "briefing_quiz_invalid",
                "each quiz question requires exactly four options",
            )
        if not 0 <= item.correct_option < QUIZ_OPTION_COUNT:
            raise BriefingError("briefing_quiz_invalid", "correct quiz option is invalid")
        cleaned.append(
            QuizEdit(
                position=item.position,
                question=_locale_map(
                    item.question,
                    require_both=require_both,
                    code="briefing_quiz_invalid",
                ),
                explanation=_locale_map(
                    item.explanation,
                    require_both=require_both,
                    code="briefing_quiz_invalid",
                ),
                options=[
                    _locale_map(
                        option,
                        require_both=require_both,
                        code="briefing_quiz_invalid",
                    )
                    for option in item.options
                ],
                correct_option=item.correct_option,
            )
        )
    return cleaned


def _clean_edit(edit: BriefingEdit, *, publishing: bool) -> BriefingEdit:
    if publishing and (edit.valid_from is None or edit.valid_to is None):
        raise BriefingError(
            "briefing_validity_required",
            "publication requires a validity start and end",
        )
    if edit.valid_from is not None and edit.valid_to is not None:
        if edit.valid_to <= edit.valid_from:
            raise BriefingError(
                "briefing_validity_invalid",
                "briefing validity end must follow its start",
            )
    body = _locale_map(
        edit.body,
        require_both=publishing,
        code="briefing_english_required",
    )
    if publishing:
        if len(body[EN_LOCALE].split()) > MAX_BRIEFING_EN_WORDS:
            raise BriefingError("briefing_too_long", "English briefing exceeds one A4 page")
        if len(body[ZH_CN_LOCALE]) > MAX_BRIEFING_ZH_CHARACTERS:
            raise BriefingError("briefing_too_long", "Chinese briefing exceeds one A4 page")
    return BriefingEdit(
        body=body,
        questions=_clean_questions(edit.questions, require_both=publishing),
        target_activity=(edit.target_activity or "").strip() or None,
        target_location=(edit.target_location or "").strip() or None,
        valid_from=edit.valid_from,
        valid_to=edit.valid_to,
    )


def _briefing_select(*, lock: bool = False) -> str:
    suffix = " for update of briefing, report" if lock else ""
    return f"""
        select
          briefing.id,
          briefing.report_id,
          briefing.version,
          briefing.body,
          briefing.status::text as status,
          briefing.target_activity,
          briefing.target_location,
          briefing.valid_from,
          briefing.valid_to,
          briefing.qr_token,
          briefing.approved_by,
          briefing.approved_at,
          briefing.created_at,
          report.human_ref,
          report.status::text as report_status,
          approver.display_name as approved_by_name
        from briefings briefing
        join reports report on report.id = briefing.report_id
        left join profiles approver on approver.id = briefing.approved_by
        where briefing.id = $1{suffix}
    """


def _question_dict(row: asyncpg.Record) -> dict[str, object]:
    return {
        "id": row["id"],
        "position": row["position"],
        "question": _decoded_json(row["question"]),
        "explanation": _decoded_json(row["explanation"]),
        "options": _decoded_json(row["options"]),
        "correct_option": row["correct_option"],
        "created_at": row["created_at"],
    }


async def _questions(
    conn: PoolConnectionProxy[asyncpg.Record],
    briefing_id: UUID,
) -> list[asyncpg.Record]:
    rows = await conn.fetch(
        """
        select * from quiz_questions
        where briefing_id = $1
        order by position
        """,
        briefing_id,
    )
    return list(rows)


def _briefing_dict(
    row: asyncpg.Record,
    question_rows: list[asyncpg.Record] | None = None,
) -> dict[str, object]:
    result = dict(row)
    result["body"] = _decoded_json(result["body"])
    result["available_transitions"] = _available_publication_transitions(row)
    if question_rows is not None:
        result["quiz_questions"] = [_question_dict(question) for question in question_rows]
    return cast(dict[str, object], result)


def _available_publication_transitions(
    row: asyncpg.Record,
) -> list[dict[str, object]]:
    """Return publication actions from server state, never from client-side role logic."""
    if row["status"] != BriefingStatus.DRAFT.value:
        return []

    report_status = ReportStatus(str(row["report_status"]))
    available: list[dict[str, object]] = []
    for target in allowed_targets(report_status, ActorType.HUMAN, Role.REVIEWER):
        transition = find(report_status, target)
        if transition is None:
            raise RuntimeError("allowed briefing target has no transition")
        if transition.event == "publish_lesson":
            available.append(
                {
                    "event": transition.event,
                    "target": transition.target.value,
                    "requires_reason": transition.requires_reason,
                }
            )

    # The report status is terminal after the first lesson is published, while the
    # product explicitly permits a versioned replacement. This operation publishes
    # the new immutable briefing without pretending the report changed status again.
    if report_status is ReportStatus.LESSON_PUBLISHED:
        available.append(
            {
                "event": "republish_lesson",
                "target": ReportStatus.LESSON_PUBLISHED.value,
                "requires_reason": False,
            }
        )
    return available


async def list_managed_briefings(actor: Actor) -> list[dict[str, object]]:
    """List every lesson version for a reviewer without exposing public token lookup."""
    _reviewer_id(actor)
    async with connection() as conn:
        rows = await conn.fetch(
            """
            select
              briefing.id,
              briefing.report_id,
              briefing.version,
              briefing.body,
              briefing.status::text as status,
              briefing.target_activity,
              briefing.target_location,
              briefing.valid_from,
              briefing.valid_to,
              briefing.qr_token,
              briefing.approved_by,
              briefing.approved_at,
              briefing.created_at,
              report.human_ref,
              report.status::text as report_status,
              count(question.id)::integer as question_count
            from briefings briefing
            join reports report on report.id = briefing.report_id
            left join quiz_questions question on question.briefing_id = briefing.id
            group by briefing.id, report.id
            order by (briefing.status = 'draft'::briefing_status) desc,
                     briefing.created_at desc, briefing.version desc
            """
        )
    return [_briefing_dict(row) for row in rows]


async def get_managed_briefing(
    briefing_id: UUID,
    actor: Actor,
) -> dict[str, object]:
    """Return one version and all editable quiz fields to a reviewer."""
    _reviewer_id(actor)
    async with connection() as conn:
        row = await conn.fetchrow(_briefing_select(), briefing_id)
        if row is None:
            raise BriefingError("briefing_not_found", "briefing does not exist")
        question_rows = await _questions(conn, briefing_id)
    return _briefing_dict(row, question_rows)


async def _write_questions(
    conn: PoolConnectionProxy[asyncpg.Record],
    briefing_id: UUID,
    questions: list[QuizEdit],
) -> None:
    await conn.executemany(
        """
        insert into quiz_questions (
          briefing_id, position, question, explanation, options, correct_option
        )
        values ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6)
        on conflict (briefing_id, position) do update set
          question = excluded.question,
          explanation = excluded.explanation,
          options = excluded.options,
          correct_option = excluded.correct_option
        """,
        [
            (
                briefing_id,
                question.position,
                json.dumps(question.question, ensure_ascii=False),
                json.dumps(question.explanation, ensure_ascii=False),
                json.dumps(question.options, ensure_ascii=False),
                question.correct_option,
            )
            for question in questions
        ],
    )


async def _update_draft(
    conn: PoolConnectionProxy[asyncpg.Record],
    briefing_id: UUID,
    edit: BriefingEdit,
) -> None:
    await conn.execute(
        """
        update briefings
        set body = $2::jsonb,
            target_activity = $3,
            target_location = $4,
            valid_from = $5,
            valid_to = $6
        where id = $1 and status = 'draft'::briefing_status
        """,
        briefing_id,
        json.dumps(edit.body, ensure_ascii=False),
        edit.target_activity,
        edit.target_location,
        edit.valid_from,
        edit.valid_to,
    )
    await _write_questions(conn, briefing_id, edit.questions)


async def _insert_revision(
    conn: PoolConnectionProxy[asyncpg.Record],
    source: asyncpg.Record,
    edit: BriefingEdit,
) -> tuple[UUID, int]:
    version = await conn.fetchval(
        "select coalesce(max(version), 0) + 1 from briefings where report_id = $1",
        source["report_id"],
    )
    if not isinstance(version, int):
        raise RuntimeError("database returned an invalid briefing version")
    briefing_id = await conn.fetchval(
        """
        insert into briefings (
          report_id, version, body, status, target_activity,
          target_location, valid_from, valid_to
        )
        values (
          $1, $2, $3::jsonb, 'draft'::briefing_status, $4, $5, $6, $7
        )
        returning id
        """,
        source["report_id"],
        version,
        json.dumps(edit.body, ensure_ascii=False),
        edit.target_activity,
        edit.target_location,
        edit.valid_from,
        edit.valid_to,
    )
    if not isinstance(briefing_id, UUID):
        raise RuntimeError("database did not return the revised briefing")
    await _write_questions(conn, briefing_id, edit.questions)
    return briefing_id, version


async def save_briefing(
    briefing_id: UUID,
    actor: Actor,
    edit: BriefingEdit,
) -> dict[str, object]:
    """Update a draft or fork a published version without touching the original."""
    profile_id = _reviewer_id(actor)
    cleaned = _clean_edit(edit, publishing=False)
    async with connection() as conn:
        async with conn.transaction():
            source = await conn.fetchrow(_briefing_select(lock=True), briefing_id)
            if source is None:
                raise BriefingError("briefing_not_found", "briefing does not exist")
            if source["status"] == BriefingStatus.DRAFT.value:
                saved_id = briefing_id
                await _update_draft(conn, saved_id, cleaned)
            elif source["status"] == BriefingStatus.PUBLISHED.value:
                saved_id, version = await _insert_revision(conn, source, cleaned)
                await conn.execute(
                    """
                    insert into audit_log (
                      report_id, actor_type, actor_id, event, source, target, metadata
                    )
                    values (
                      $1, 'human'::actor_type, $2, 'revise_lesson',
                      $3::report_status, $3::report_status, $4::jsonb
                    )
                    """,
                    source["report_id"],
                    profile_id,
                    source["report_status"],
                    json.dumps(
                        {
                            "source_briefing_id": str(briefing_id),
                            "briefing_id": str(saved_id),
                            "briefing_version": version,
                        }
                    ),
                )
            else:
                raise BriefingError("briefing_not_editable", "briefing status is not editable")
            saved = await conn.fetchrow(_briefing_select(), saved_id)
            if saved is None:
                raise RuntimeError("saved briefing disappeared")
            question_rows = await _questions(conn, saved_id)
    return _briefing_dict(saved, question_rows)


def _new_qr_token() -> str:
    return secrets.token_urlsafe(QR_TOKEN_BYTES)


async def publish_briefing(
    briefing_id: UUID,
    actor: Actor,
) -> dict[str, object]:
    """Publish metadata and the first report transition in one transaction."""
    profile_id = _reviewer_id(actor)
    async with connection() as conn:
        async with conn.transaction():
            source = await conn.fetchrow(_briefing_select(lock=True), briefing_id)
            if source is None:
                raise BriefingError("briefing_not_found", "briefing does not exist")
            if source["status"] != BriefingStatus.DRAFT.value:
                raise BriefingError("briefing_not_draft", "only a draft can be published")
            question_rows = await _questions(conn, briefing_id)
            edit = BriefingEdit(
                body=cast(dict[str, str], _decoded_json(source["body"])),
                questions=[
                    QuizEdit(
                        position=int(question["position"]),
                        question=cast(
                            dict[str, str],
                            _decoded_json(question["question"]),
                        ),
                        explanation=cast(
                            dict[str, str],
                            _decoded_json(question["explanation"]),
                        ),
                        options=cast(
                            list[dict[str, str]],
                            _decoded_json(question["options"]),
                        ),
                        correct_option=int(question["correct_option"]),
                    )
                    for question in question_rows
                ],
                target_activity=cast(str | None, source["target_activity"]),
                target_location=cast(str | None, source["target_location"]),
                valid_from=cast(datetime | None, source["valid_from"]),
                valid_to=cast(datetime | None, source["valid_to"]),
            )
            _clean_edit(edit, publishing=True)
            token = _new_qr_token()
            if await conn.fetchval(
                "select exists(select 1 from briefings where qr_token = $1)", token
            ):
                raise BriefingError(
                    "briefing_token_conflict",
                    "generated briefing token already exists",
                )
            published = await conn.fetchrow(
                """
                update briefings
                set status = 'published'::briefing_status,
                    qr_token = $2,
                    approved_by = $3,
                    approved_at = now()
                where id = $1 and status = 'draft'::briefing_status
                returning id, report_id, version
                """,
                briefing_id,
                token,
                profile_id,
            )
            if published is None:
                raise BriefingError("briefing_publish_conflict", "briefing changed before publish")

            report_status = ReportStatus(str(source["report_status"]))
            metadata = {
                "briefing_id": str(briefing_id),
                "briefing_version": int(source["version"]),
            }
            if report_status is ReportStatus.LESSON_DRAFTED:
                await transition_report(
                    cast(UUID, source["report_id"]),
                    ReportStatus.LESSON_PUBLISHED,
                    actor,
                    metadata=metadata,
                    transaction_connection=conn,
                )
            elif report_status is ReportStatus.LESSON_PUBLISHED:
                await conn.execute(
                    """
                    insert into audit_log (
                      report_id, actor_type, actor_id, event, source, target, metadata
                    )
                    values (
                      $1, 'human'::actor_type, $2, 'republish_lesson',
                      'lesson_published'::report_status,
                      'lesson_published'::report_status, $3::jsonb
                    )
                    """,
                    source["report_id"],
                    profile_id,
                    json.dumps(metadata),
                )
            else:
                raise BriefingError(
                    "briefing_report_state_invalid",
                    "report is not ready to publish a lesson",
                )

            result = await conn.fetchrow(_briefing_select(), briefing_id)
            if result is None:
                raise RuntimeError("published briefing disappeared")
            result_questions = await _questions(conn, briefing_id)
    return _briefing_dict(result, result_questions)
