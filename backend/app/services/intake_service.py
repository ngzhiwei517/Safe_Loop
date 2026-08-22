"""Keep durable clarification state outside the restartable AI graph."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Literal, cast
from uuid import UUID

import asyncpg

from app.ai.intake_graph import (
    IntakeState,
    MAX_CLARIFICATION_QUESTIONS,
    MAX_CLARIFICATION_ROUNDS,
    MAX_QUESTIONS_PER_ROUND,
    PriorAnswer,
    intake_graph,
)
from app.db import connection
from app.domain.enums import ActorType, ReportStatus, Role
from app.services.draft_service import append_draft
from app.services.report_service import Actor, transition_report

logger = logging.getLogger(__name__)

Locale = Literal["en", "zh-CN"]


class ClarificationError(Exception):
    """Carry a stable answer error code to the HTTP boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ClarificationAnswer:
    """Return the stored answer and whether a completed round needs processing."""

    clarification: asyncpg.Record
    rerun: bool


@dataclass(frozen=True)
class _LoadedIntake:
    status: ReportStatus
    state: IntakeState


def _locale(value: object) -> Locale:
    return cast(Locale, value if value in {"en", "zh-CN"} else "en")


async def _load_intake(report_id: UUID) -> _LoadedIntake | None:
    async with connection() as conn:
        report = await conn.fetchrow(
            """
            select reports.*, profiles.preferred_lang
            from reports
            join profiles on profiles.id = reports.reporter_id
            where reports.id = $1
            """,
            report_id,
        )
        if report is None:
            return None
        status = ReportStatus(report["status"])
        if status not in {ReportStatus.SUBMITTED, ReportStatus.CLARIFYING}:
            return None
        if status is ReportStatus.CLARIFYING:
            has_pending = await conn.fetchval(
                """
                select exists (
                  select 1 from clarifications
                  where report_id = $1 and answer is null
                )
                """,
                report_id,
            )
            if has_pending:
                return None

        answer_rows = await conn.fetch(
            """
            select gap, question, answer
            from clarifications
            where report_id = $1 and answer is not null
            order by round, created_at, id
            """,
            report_id,
        )
        prior_answers: list[PriorAnswer] = [
            {
                "gap": str(row["gap"]),
                "question": str(row["question"]),
                "answer": str(row["answer"]),
            }
            for row in answer_rows
        ]
        state: IntakeState = {
            "report_id": str(report_id),
            "lang_original": _locale(report["lang_original"]),
            "preferred_lang": _locale(report["preferred_lang"]),
            "description_original": str(report["description_original"]),
            "description_en": cast(str | None, report["description_en"]),
            "location": cast(str | None, report["location_text"]),
            "activity": cast(str | None, report["activity"]),
            "prior_answers": prior_answers,
            "round": int(report["clarify_rounds"]),
            "observed_facts": [],
            "assumptions": [],
            "missing_information": [],
            "questions": [],
            "draft": None,
        }
        return _LoadedIntake(status, state)


async def _invoke_graph(state: IntakeState) -> IntakeState:
    result = await intake_graph.ainvoke(state)
    if type(result) is not dict:
        raise TypeError("intake graph must return a plain dict")
    return cast(IntakeState, result)


def _validate_questions(state: IntakeState, result: IntakeState) -> None:
    questions = result["questions"]
    unresolved = set(result["missing_information"])
    if len(questions) > MAX_QUESTIONS_PER_ROUND:
        raise ValueError("intake graph exceeded the question cap")
    if len(state["prior_answers"]) + len(questions) > MAX_CLARIFICATION_QUESTIONS:
        raise ValueError("intake graph exceeded the report question cap")
    if state["round"] >= MAX_CLARIFICATION_ROUNDS and questions:
        raise ValueError("intake graph exceeded the clarification round cap")
    if len({question["gap"] for question in questions}) != len(questions):
        raise ValueError("intake graph returned duplicate clarification gaps")
    if any(
        not question["gap"].strip()
        or not question["text"].strip()
        or question["gap"] not in unresolved
        for question in questions
    ):
        raise ValueError("intake graph returned an invalid clarification question")
    if questions and result["draft"] is not None:
        raise ValueError("clarification result cannot also contain a draft")
    if not questions and result["draft"] is None:
        raise ValueError("completed intake result must contain a draft")


async def _persist_result(
    report_id: UUID,
    loaded: _LoadedIntake,
    result: IntakeState,
) -> bool:
    _validate_questions(loaded.state, result)
    async with connection() as conn:
        async with conn.transaction():
            report = await conn.fetchrow(
                """
                select status::text, clarify_rounds
                from reports
                where id = $1
                for update
                """,
                report_id,
            )
            if report is None or ReportStatus(report["status"]) is not loaded.status:
                return False
            has_pending = await conn.fetchval(
                """
                select exists (
                  select 1 from clarifications
                  where report_id = $1 and answer is null
                )
                """,
                report_id,
            )
            if has_pending:
                return False

            questions = result["questions"]
            await conn.execute(
                """
                update reports
                set description_en = $2,
                    missing_information = $3::jsonb
                where id = $1
                """,
                report_id,
                result["description_en"],
                json.dumps(result["missing_information"]),
            )
            if questions:
                current_round = int(report["clarify_rounds"])
                next_round = current_round + 1
                if next_round > MAX_CLARIFICATION_ROUNDS:
                    raise ValueError("clarification round cap reached")
                await conn.executemany(
                    """
                    insert into clarifications (report_id, round, gap, question)
                    values ($1, $2, $3, $4)
                    """,
                    [
                        (
                            report_id,
                            next_round,
                            question["gap"],
                            question["text"],
                        )
                        for question in questions
                    ],
                )
                if loaded.status is ReportStatus.SUBMITTED:
                    await transition_report(
                        report_id,
                        ReportStatus.CLARIFYING,
                        Actor.ai(),
                        transaction_connection=conn,
                    )
                return True

            draft_envelope = result["draft"]
            if draft_envelope is None:
                raise ValueError("completed intake result must contain a draft")
            await append_draft(
                report_id,
                draft_envelope,
                transaction_connection=conn,
            )
            await transition_report(
                report_id,
                ReportStatus.AI_DRAFTED,
                Actor.ai(),
                transaction_connection=conn,
            )
            return True


async def run_intake(report_id: UUID) -> bool:
    """Run one restartable graph pass and fail closed on every exception."""
    try:
        loaded = await _load_intake(report_id)
        if loaded is None:
            return False
        result = await _invoke_graph(loaded.state)
        return await _persist_result(report_id, loaded, result)
    except Exception:
        logger.exception("intake_graph_failed", extra={"report_id": str(report_id)})
        return False


async def list_report_clarifications(report_id: UUID) -> list[asyncpg.Record]:
    """Return the durable question history without changing answer state."""
    async with connection() as conn:
        return await conn.fetch(
            """
            select id, report_id, round, gap, question, answer, answered_at, created_at
            from clarifications
            where report_id = $1
            order by round, created_at, id
            """,
            report_id,
        )


async def answer_clarification(
    report_id: UUID,
    clarification_id: UUID,
    actor: Actor,
    answer: str,
) -> ClarificationAnswer:
    """Store one reporter answer and complete its round exactly once."""
    if (
        actor.actor_type is not ActorType.HUMAN
        or actor.role is not Role.REPORTER
        or actor.profile_id is None
    ):
        raise ClarificationError(
            "clarification_actor_forbidden",
            "a reporter profile is required",
        )
    if not answer.strip():
        raise ClarificationError(
            "clarification_answer_required",
            "clarification answer is required",
        )

    async with connection() as conn:
        async with conn.transaction():
            report = await conn.fetchrow(
                """
                select reporter_id, status::text, clarify_rounds
                from reports
                where id = $1
                for update
                """,
                report_id,
            )
            if report is None:
                raise ClarificationError(
                    "report_not_found",
                    "report does not exist",
                )
            if report["reporter_id"] != actor.profile_id:
                raise ClarificationError(
                    "clarification_forbidden",
                    "clarification belongs to another reporter",
                )
            if ReportStatus(report["status"]) is not ReportStatus.CLARIFYING:
                raise ClarificationError(
                    "report_not_clarifying",
                    "report is not awaiting clarification",
                )

            clarification = await conn.fetchrow(
                """
                select * from clarifications
                where id = $1 and report_id = $2
                for update
                """,
                clarification_id,
                report_id,
            )
            if clarification is None:
                raise ClarificationError(
                    "clarification_not_found",
                    "clarification does not exist",
                )
            if clarification["answer"] is not None:
                raise ClarificationError(
                    "clarification_already_answered",
                    "clarification was already answered",
                )
            expected_round = int(report["clarify_rounds"]) + 1
            question_round = int(clarification["round"])
            if question_round != expected_round:
                raise ClarificationError(
                    "clarification_round_invalid",
                    "clarification is not in the active round",
                )

            stored = await conn.fetchrow(
                """
                update clarifications
                set answer = $2, answered_at = now()
                where id = $1
                returning *
                """,
                clarification_id,
                answer.strip(),
            )
            if stored is None:
                raise RuntimeError("clarification disappeared while answering")
            unanswered = await conn.fetchval(
                """
                select count(*)
                from clarifications
                where report_id = $1 and round = $2 and answer is null
                """,
                report_id,
                question_round,
            )
            rerun = int(unanswered) == 0
            if rerun:
                updated = await conn.execute(
                    """
                    update reports
                    set clarify_rounds = $2
                    where id = $1 and clarify_rounds = $3
                    """,
                    report_id,
                    question_round,
                    question_round - 1,
                )
                if updated != "UPDATE 1":
                    raise RuntimeError("clarification round changed concurrently")
            return ClarificationAnswer(stored, rerun)
