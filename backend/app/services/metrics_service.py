"""Compute one internally consistent operational snapshot for human reviewers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import json
from typing import cast
from uuid import UUID

from app.db import connection
from app.domain.enums import ActorType, ReportStatus, Role
from app.services.report_service import Actor

OPEN_REPORT_STATUSES = (
    ReportStatus.DRAFT,
    ReportStatus.SUBMITTED,
    ReportStatus.CLARIFYING,
    ReportStatus.AI_DRAFTED,
    ReportStatus.UNDER_REVIEW,
    ReportStatus.INFO_REQUESTED,
    ReportStatus.ESCALATED,
    ReportStatus.ACTION_ASSIGNED,
    ReportStatus.ACTION_SUBMITTED,
)

REPEAT_HAZARD_WINDOW_DAYS = 90


class MetricsError(Exception):
    """Carry a stable metrics error code to the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class QuestionPerformance:
    """Describe first-attempt outcomes without retry inflation."""

    question_id: UUID
    briefing_id: UUID
    position: int
    question: dict[str, str]
    first_attempt_count: int
    first_attempt_correct_count: int
    first_attempt_wrong_count: int
    first_attempt_pass_rate: float | None


@dataclass(frozen=True)
class ResponsibleRework:
    """Expose the responsible assignee used as the v1 subcontractor proxy."""

    profile_id: UUID
    display_name: str
    action_count: int
    reworked_action_count: int
    rework_rate: float


@dataclass(frozen=True)
class RepeatHazardCluster:
    """Group human-closed hazards that recur at one normalized location."""

    category: str
    location: str
    report_count: int
    recurrence_count: int
    first_closed_at: datetime
    latest_closed_at: datetime
    responsible_rework: tuple[ResponsibleRework, ...]


@dataclass(frozen=True)
class MetricsSummary:
    """Keep metric names and units explicit at the API boundary."""

    open_by_status: dict[str, int]
    overdue_count: int
    rework_rate: float
    median_verification_cycles_to_close: float | None
    median_submitted_to_under_review_seconds: float | None
    median_submitted_to_action_assigned_seconds: float | None
    median_action_assigned_to_verified_closed_seconds: float | None
    reviewer_correction_rate: float
    published_briefing_count: int
    crew_reach: int
    anonymous_quiz_response_count: int
    first_attempt_count: int
    first_attempt_pass_rate: float | None
    question_performance: tuple[QuestionPerformance, ...]
    questions_most_often_wrong: tuple[QuestionPerformance, ...]
    repeat_hazard_window_days: int
    repeat_hazards: tuple[RepeatHazardCluster, ...]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    raise RuntimeError("database returned a non-numeric metric")


def _locale_map(value: object) -> dict[str, str]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise RuntimeError("database returned a non-object locale map")
    result: dict[str, str] = {}
    for key, item in decoded.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise RuntimeError("database returned an invalid locale map")
        result[key] = item
    return result


def _responsible_rework(value: object) -> tuple[ResponsibleRework, ...]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, list):
        raise RuntimeError("database returned invalid responsible rework data")
    result: list[ResponsibleRework] = []
    for item in decoded:
        if not isinstance(item, dict):
            raise RuntimeError("database returned invalid responsible rework data")
        result.append(
            ResponsibleRework(
                profile_id=UUID(str(item["profile_id"])),
                display_name=str(item["display_name"]),
                action_count=int(item["action_count"]),
                reworked_action_count=int(item["reworked_action_count"]),
                rework_rate=float(item["rework_rate"]),
            )
        )
    return tuple(result)


async def get_metrics_summary(actor: Actor) -> MetricsSummary:
    """Return lifetime workflow metrics from one repeatable-read snapshot."""
    if actor.actor_type is not ActorType.HUMAN or actor.role not in {
        Role.REVIEWER,
        Role.ADMIN,
    }:
        raise MetricsError(
            "metrics_actor_forbidden",
            "metrics require a reviewer or administrator",
        )

    status_values = [status.value for status in OPEN_REPORT_STATUSES]
    async with connection() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            status_rows = await conn.fetch(
                """
                select status::text as status, count(*)::integer as report_count
                from reports
                where status = any($1::report_status[])
                group by status
                """,
                status_values,
            )
            summary = await conn.fetchrow(
                """
                with action_summary as (
                  select
                    count(*)::integer as action_count,
                    count(*) filter (
                      where action.rework_count >= 1
                    )::integer as reworked_action_count,
                    count(*) filter (
                      where action.status = 'assigned'::action_status
                        and action.due_at < now()
                        and assignment.active
                        and report.status = 'action_assigned'::report_status
                    )::integer as overdue_count
                  from corrective_actions action
                  join report_assignments assignment
                    on assignment.id = action.assignment_id
                   and assignment.report_id = action.report_id
                  join reports report on report.id = action.report_id
                ),
                report_event_times as (
                  select
                    report.id as report_id,
                    report.submitted_at,
                    report.closed_at,
                    min(event.created_at) filter (
                      where event.target = 'under_review'::report_status
                    ) as under_review_at,
                    min(event.created_at) filter (
                      where event.target = 'action_assigned'::report_status
                    ) as action_assigned_at
                  from reports report
                  left join audit_log event on event.report_id = report.id
                  group by report.id
                ),
                closed_cycles as (
                  select
                    report.id as report_id,
                    count(verification.id)::double precision as cycles
                  from reports report
                  join verifications verification
                    on verification.report_id = report.id
                  where report.closed_at is not null
                  group by report.id
                ),
                reviewed_reports as (
                  select
                    report_id,
                    bool_or(
                      corrections is not null and corrections <> '{}'::jsonb
                    ) as corrected
                  from review_decisions
                  group by report_id
                )
                select
                  action_summary.overdue_count,
                  coalesce(
                    action_summary.reworked_action_count::double precision
                      / nullif(action_summary.action_count, 0),
                    0
                  ) as rework_rate,
                  (
                    select percentile_cont(0.5) within group (order by cycles)
                    from closed_cycles
                  ) as median_verification_cycles_to_close,
                  (
                    select percentile_cont(0.5) within group (
                      order by extract(epoch from under_review_at - submitted_at)
                    )
                    from report_event_times
                    where submitted_at is not null and under_review_at is not null
                  ) as median_submitted_to_under_review_seconds,
                  (
                    select percentile_cont(0.5) within group (
                      order by extract(epoch from action_assigned_at - submitted_at)
                    )
                    from report_event_times
                    where submitted_at is not null and action_assigned_at is not null
                  ) as median_submitted_to_action_assigned_seconds,
                  (
                    select percentile_cont(0.5) within group (
                      order by extract(epoch from closed_at - action_assigned_at)
                    )
                    from report_event_times
                    where closed_at is not null and action_assigned_at is not null
                  ) as median_action_assigned_to_verified_closed_seconds,
                  coalesce(
                    (
                      select count(*) filter (where corrected)::double precision
                        / nullif(count(*), 0)
                      from reviewed_reports
                    ),
                    0
                  ) as reviewer_correction_rate
                from action_summary
                """
            )
            learning = await conn.fetchrow(
                """
                with eligible_responses as (
                  select
                    response.id,
                    response.question_id,
                    response.respondent_id,
                    response.is_correct,
                    response.created_at
                  from quiz_responses response
                  join quiz_questions question on question.id = response.question_id
                  join briefings briefing on briefing.id = question.briefing_id
                  where briefing.status = 'published'::briefing_status
                ),
                ranked_identified_responses as (
                  select *, row_number() over (
                    partition by question_id, respondent_id
                    order by created_at, id
                  ) as attempt_number
                  from eligible_responses
                  where respondent_id is not null
                ),
                first_attempts as (
                  select is_correct
                  from ranked_identified_responses
                  where attempt_number = 1
                )
                select
                  (
                    select count(distinct report_id)::integer
                    from briefings
                    where status = 'published'::briefing_status
                  ) as published_briefing_count,
                  (
                    select count(distinct respondent_id)::integer
                    from eligible_responses
                    where respondent_id is not null
                  ) as crew_reach,
                  (
                    select count(*)::integer
                    from eligible_responses
                    where respondent_id is null
                  ) as anonymous_quiz_response_count,
                  (select count(*)::integer from first_attempts) as first_attempt_count,
                  (
                    select count(*) filter (where is_correct)::double precision
                      / nullif(count(*), 0)
                    from first_attempts
                  ) as first_attempt_pass_rate
                """
            )
            question_rows = await conn.fetch(
                """
                with ranked_responses as (
                  select
                    response.question_id,
                    response.is_correct,
                    row_number() over (
                      partition by response.question_id, response.respondent_id
                      order by response.created_at, response.id
                    ) as attempt_number
                  from quiz_responses response
                  join quiz_questions question on question.id = response.question_id
                  join briefings briefing on briefing.id = question.briefing_id
                  where response.respondent_id is not null
                    and briefing.status = 'published'::briefing_status
                ),
                first_attempts as (
                  select question_id, is_correct
                  from ranked_responses
                  where attempt_number = 1
                )
                select
                  question.id as question_id,
                  question.briefing_id,
                  question.position,
                  question.question,
                  count(first_attempts.question_id)::integer as first_attempt_count,
                  count(first_attempts.question_id) filter (
                    where first_attempts.is_correct
                  )::integer as first_attempt_correct_count,
                  count(first_attempts.question_id) filter (
                    where not first_attempts.is_correct
                  )::integer as first_attempt_wrong_count,
                  count(first_attempts.question_id) filter (
                    where first_attempts.is_correct
                  )::double precision
                    / nullif(count(first_attempts.question_id), 0)
                    as first_attempt_pass_rate
                from quiz_questions question
                join briefings briefing on briefing.id = question.briefing_id
                left join first_attempts on first_attempts.question_id = question.id
                where briefing.status = 'published'::briefing_status
                group by
                  question.id, question.briefing_id, question.position,
                  question.question, briefing.approved_at
                order by briefing.approved_at desc, question.position, question.id
                """
            )
            repeat_rows = await conn.fetch(
                """
                with closed_reports as (
                  select
                    report.id,
                    report.closed_at,
                    btrim(report.location_text) as location,
                    lower(regexp_replace(btrim(report.location_text), '\\s+', ' ', 'g'))
                      as location_key,
                    coalesce(
                      (
                        select decision.corrections #>> '{category,after}'
                        from review_decisions decision
                        where decision.report_id = report.id
                          and nullif(
                            btrim(decision.corrections #>> '{category,after}'),
                            ''
                          ) is not null
                        order by decision.created_at desc, decision.id desc
                        limit 1
                      ),
                      (
                        select draft.proposed_category
                        from ai_drafts draft
                        where draft.report_id = report.id
                          and nullif(btrim(draft.proposed_category), '') is not null
                        order by draft.version desc, draft.id desc
                        limit 1
                      )
                    ) as category
                  from reports report
                  where report.closed_at >= now() - interval '180 days'
                    and report.status in (
                      'verified_closed'::report_status,
                      'lesson_drafted'::report_status,
                      'lesson_published'::report_status
                    )
                    and nullif(btrim(report.location_text), '') is not null
                ),
                normalized_reports as (
                  select
                    *,
                    lower(regexp_replace(btrim(category), '\\s+', ' ', 'g'))
                      as category_key
                  from closed_reports
                  where nullif(btrim(category), '') is not null
                ),
                ordered_reports as (
                  select
                    *,
                    lag(id) over (
                      partition by category_key, location_key
                      order by closed_at, id
                    ) as previous_report_id,
                    lag(closed_at) over (
                      partition by category_key, location_key
                      order by closed_at, id
                    ) as previous_closed_at
                  from normalized_reports
                ),
                recurrence_events as (
                  select
                    category_key,
                    location_key,
                    id as report_id,
                    previous_report_id,
                    closed_at
                  from ordered_reports
                  where previous_report_id is not null
                    and previous_closed_at is not null
                    and closed_at - previous_closed_at <= interval '90 days'
                    and closed_at >= now() - interval '90 days'
                ),
                cluster_report_ids as (
                  select category_key, location_key, report_id
                  from recurrence_events
                  union
                  select category_key, location_key, previous_report_id
                  from recurrence_events
                ),
                clusters as (
                  select
                    participant.category_key,
                    participant.location_key,
                    min(report.category) as category,
                    min(report.location) as location,
                    count(*)::integer as report_count,
                    (
                      select count(*)::integer
                      from recurrence_events event
                      where event.category_key = participant.category_key
                        and event.location_key = participant.location_key
                    ) as recurrence_count,
                    min(report.closed_at) as first_closed_at,
                    max(report.closed_at) as latest_closed_at,
                    array_agg(report.id) as report_ids
                  from cluster_report_ids participant
                  join normalized_reports report on report.id = participant.report_id
                  group by participant.category_key, participant.location_key
                ),
                cluster_responsibles as (
                  select distinct
                    cluster.category_key,
                    cluster.location_key,
                    assignment.assignee_id
                  from clusters cluster
                  cross join lateral unnest(cluster.report_ids)
                    as clustered_report(report_id)
                  join report_assignments assignment
                    on assignment.report_id = clustered_report.report_id
                ),
                responsible_stats as (
                  select
                    assignment.assignee_id,
                    count(action.id)::integer as action_count,
                    count(action.id) filter (
                      where action.rework_count >= 1
                    )::integer as reworked_action_count
                  from report_assignments assignment
                  join corrective_actions action
                    on action.assignment_id = assignment.id
                  group by assignment.assignee_id
                )
                select
                  cluster.category,
                  cluster.location,
                  cluster.report_count,
                  cluster.recurrence_count,
                  cluster.first_closed_at,
                  cluster.latest_closed_at,
                  coalesce(
                    (
                      select jsonb_agg(
                        jsonb_build_object(
                          'profile_id', profile.id,
                          'display_name', profile.display_name,
                          'action_count', coalesce(stats.action_count, 0),
                          'reworked_action_count',
                            coalesce(stats.reworked_action_count, 0),
                          'rework_rate', coalesce(
                            stats.reworked_action_count::double precision
                              / nullif(stats.action_count, 0),
                            0
                          )
                        )
                        order by profile.display_name, profile.id
                      )
                      from cluster_responsibles responsible
                      join profiles profile on profile.id = responsible.assignee_id
                      left join responsible_stats stats
                        on stats.assignee_id = responsible.assignee_id
                      where responsible.category_key = cluster.category_key
                        and responsible.location_key = cluster.location_key
                    ),
                    '[]'::jsonb
                  ) as responsible_rework
                from clusters cluster
                order by
                  cluster.latest_closed_at desc,
                  cluster.report_count desc,
                  cluster.category_key,
                  cluster.location_key
                """
            )
    if summary is None:
        raise RuntimeError("database did not return metrics summary")
    if learning is None:
        raise RuntimeError("database did not return learning metrics")

    open_by_status = {status.value: 0 for status in OPEN_REPORT_STATUSES}
    for row in status_rows:
        open_by_status[str(row["status"])] = int(row["report_count"])
    question_performance = tuple(
        QuestionPerformance(
            question_id=cast(UUID, row["question_id"]),
            briefing_id=cast(UUID, row["briefing_id"]),
            position=int(row["position"]),
            question=_locale_map(row["question"]),
            first_attempt_count=int(row["first_attempt_count"]),
            first_attempt_correct_count=int(row["first_attempt_correct_count"]),
            first_attempt_wrong_count=int(row["first_attempt_wrong_count"]),
            first_attempt_pass_rate=_optional_float(row["first_attempt_pass_rate"]),
        )
        for row in question_rows
    )
    questions_most_often_wrong = tuple(
        sorted(
            (
                question
                for question in question_performance
                if question.first_attempt_wrong_count > 0
            ),
            key=lambda question: (
                -question.first_attempt_wrong_count,
                question.first_attempt_pass_rate
                if question.first_attempt_pass_rate is not None
                else 1.0,
                str(question.question_id),
            ),
        )[:5]
    )
    repeat_hazards = tuple(
        RepeatHazardCluster(
            category=str(row["category"]),
            location=str(row["location"]),
            report_count=int(row["report_count"]),
            recurrence_count=int(row["recurrence_count"]),
            first_closed_at=cast(datetime, row["first_closed_at"]),
            latest_closed_at=cast(datetime, row["latest_closed_at"]),
            responsible_rework=_responsible_rework(row["responsible_rework"]),
        )
        for row in repeat_rows
    )
    return MetricsSummary(
        open_by_status=open_by_status,
        overdue_count=int(summary["overdue_count"]),
        rework_rate=float(summary["rework_rate"]),
        median_verification_cycles_to_close=_optional_float(
            summary["median_verification_cycles_to_close"]
        ),
        median_submitted_to_under_review_seconds=_optional_float(
            summary["median_submitted_to_under_review_seconds"]
        ),
        median_submitted_to_action_assigned_seconds=_optional_float(
            summary["median_submitted_to_action_assigned_seconds"]
        ),
        median_action_assigned_to_verified_closed_seconds=_optional_float(
            summary["median_action_assigned_to_verified_closed_seconds"]
        ),
        reviewer_correction_rate=float(summary["reviewer_correction_rate"]),
        published_briefing_count=int(learning["published_briefing_count"]),
        crew_reach=int(learning["crew_reach"]),
        anonymous_quiz_response_count=int(
            learning["anonymous_quiz_response_count"]
        ),
        first_attempt_count=int(learning["first_attempt_count"]),
        first_attempt_pass_rate=_optional_float(learning["first_attempt_pass_rate"]),
        question_performance=question_performance,
        questions_most_often_wrong=questions_most_often_wrong,
        repeat_hazard_window_days=REPEAT_HAZARD_WINDOW_DAYS,
        repeat_hazards=repeat_hazards,
    )
