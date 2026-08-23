"""Compute one internally consistent operational snapshot for human reviewers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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


class MetricsError(Exception):
    """Carry a stable metrics error code to the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    raise RuntimeError("database returned a non-numeric metric")


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
    if summary is None:
        raise RuntimeError("database did not return metrics summary")

    open_by_status = {status.value: 0 for status in OPEN_REPORT_STATUSES}
    for row in status_rows:
        open_by_status[str(row["status"])] = int(row["report_count"])
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
    )
