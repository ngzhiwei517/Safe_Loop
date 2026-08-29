"use client";

import {
  ArrowTrendingUpIcon,
  BellIcon,
  ExclamationTriangleIcon,
  UserGroupIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  defaultLocale,
  formatDate,
  formatDurationSeconds,
  formatNumber,
  formatPercent,
  isLocale,
  locales,
} from "../../lib/locales";
import { getMetricsSummary, type MetricsSummary } from "../../lib/metrics";
import { reportStatuses } from "../../lib/stateMachine";
import { createClient } from "../../lib/supabase/browser";
import {
  type OperationsRole,
  useOperationsNavigation,
} from "../navigation/useOperationsNavigation";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { StatusChip } from "../ui/StatusChip";

function MetricCard({
  value,
  label,
  tone = "default",
}: {
  value: string;
  label: string;
  tone?: "default" | "danger" | "success";
}) {
  const valueClass =
    tone === "danger"
      ? "text-danger"
      : tone === "success"
        ? "text-successStrong"
        : "text-ink";
  return (
    <Card className="space-y-1">
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
      <p className="text-sm font-bold text-inkMuted">{label}</p>
    </Card>
  );
}

export function DashboardPage({
  requestedLocale,
  role = "reviewer",
}: {
  requestedLocale: string;
  role?: OperationsRole;
}) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const navItems = useOperationsNavigation(locale, role);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      setMetrics(await getMetricsSummary(session.access_token));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const languageSwitch = (
    <LanguageSwitch
      current={locale}
      label={t("app.language")}
      options={[
        { value: locales[0], label: t("app.languageEnglish") },
        { value: locales[1], label: t("app.languageChinese") },
      ]}
    />
  );
  const openTotal = metrics
    ? Object.values(metrics.open_by_status).reduce(
        (total, count) => total + (count ?? 0),
        0,
      )
    : 0;
  const duration = (value: number | null) =>
    value === null
      ? t("dashboard.notAvailable")
      : formatDurationSeconds(value, locale);

  return (
    <AppShell
      title={t("dashboard.title")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={0}
      pollStatus
      showUrgentAlerts
      alertsHref={`/${locale}/alerts`}
      navItems={navItems}
      activeHref={`/${locale}/dashboard`}
      languageSwitch={languageSwitch}
    >
      <section className="space-y-5 pb-6 pt-3">
        <p className="text-sm font-bold text-inkMuted">{t("dashboard.scope")}</p>
        {failed && (
          <Banner
            tone="warning"
            title={t("dashboard.failureTitle")}
            detail={t("dashboard.failureDetail")}
          />
        )}
        {loading ? (
          <p className="py-8 text-center text-base text-inkMuted" role="status">
            {t("dashboard.loading")}
          </p>
        ) : metrics ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <MetricCard
                value={formatNumber(openTotal, locale)}
                label={t("dashboard.openCases")}
              />
              <MetricCard
                value={formatNumber(metrics.overdue_count, locale)}
                label={t("dashboard.overdue")}
                tone={metrics.overdue_count > 0 ? "danger" : "success"}
              />
              <MetricCard
                value={formatPercent(metrics.rework_rate, locale)}
                label={t("dashboard.reworkRate")}
                tone={metrics.rework_rate > 0 ? "danger" : "default"}
              />
              <MetricCard
                value={
                  metrics.median_verification_cycles_to_close === null
                    ? t("dashboard.notAvailable")
                    : formatNumber(
                        metrics.median_verification_cycles_to_close,
                        locale,
                      )
                }
                label={t("dashboard.medianCycles")}
              />
            </div>

            <div className="space-y-3">
              <h2 className="text-base font-bold text-ink">
                {t("dashboard.learningOutcomes")}
              </h2>
              <Card className="border-success bg-successSurface">
                <div className="flex items-start gap-3">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-control bg-successTint text-successStrong">
                    <ArrowTrendingUpIcon className="h-6 w-6" />
                  </span>
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="text-sm font-bold text-successStrong">
                      {t("dashboard.learningQuestion")}
                    </p>
                    <p className="text-4xl font-bold text-ink">
                      {metrics.first_attempt_pass_rate === null
                        ? t("dashboard.notAvailable")
                        : formatPercent(metrics.first_attempt_pass_rate, locale)}
                    </p>
                    <p className="text-sm font-bold text-ink">
                      {t("dashboard.firstAttemptPassRate")}
                    </p>
                    <p className="text-sm text-inkMuted">
                      {t("dashboard.firstAttemptBasis", {
                        count: metrics.first_attempt_count,
                      })}
                    </p>
                  </div>
                </div>
              </Card>

              <div className="grid grid-cols-2 gap-3">
                <MetricCard
                  value={formatNumber(metrics.published_briefing_count, locale)}
                  label={t("dashboard.publishedBriefings")}
                />
                <MetricCard
                  value={formatNumber(metrics.crew_reach, locale)}
                  label={t("dashboard.crewReach")}
                />
              </div>
              <p className="text-sm leading-5 text-inkMuted">
                {t("dashboard.crewReachDefinition")}
              </p>
              {metrics.anonymous_quiz_response_count > 0 && (
                <p className="rounded-control bg-surfaceSunken px-3 py-2 text-sm leading-5 text-inkMuted">
                  {t("dashboard.anonymousExcluded", {
                    count: metrics.anonymous_quiz_response_count,
                  })}
                </p>
              )}
            </div>

            <div className="space-y-3">
              <h2 className="text-base font-bold text-ink">
                {t("dashboard.questionPerformance")}
              </h2>
              {metrics.question_performance.length === 0 ? (
                <Card>
                  <p className="text-sm text-inkMuted">
                    {t("dashboard.noQuestionAttempts")}
                  </p>
                </Card>
              ) : (
                <Card className="divide-y divide-border py-1">
                  {metrics.question_performance.map((question) => {
                    const rate = question.first_attempt_pass_rate;
                    return (
                      <div className="space-y-2 py-4" key={question.question_id}>
                        <div className="flex items-start justify-between gap-3">
                          <p className="min-w-0 text-sm font-bold leading-5 text-ink">
                            {question.question[locale] ||
                              question.question[locales[0]]}
                          </p>
                          <span className="shrink-0 text-sm font-bold text-ink">
                            {rate === null
                              ? t("dashboard.notAvailable")
                              : formatPercent(rate, locale)}
                          </span>
                        </div>
                        <div
                          aria-label={t("dashboard.questionPassRateLabel")}
                          aria-valuemax={100}
                          aria-valuemin={0}
                          aria-valuenow={rate === null ? undefined : rate * 100}
                          className="h-2 overflow-hidden rounded-chip bg-surfaceSunken"
                          role="progressbar"
                        >
                          <span
                            className="block h-full rounded-chip bg-success"
                            style={{ width: `${(rate ?? 0) * 100}%` }}
                          />
                        </div>
                        <p className="text-xs text-inkMuted">
                          {t("dashboard.questionAttemptSummary", {
                            attempts: question.first_attempt_count,
                            wrong: question.first_attempt_wrong_count,
                          })}
                        </p>
                      </div>
                    );
                  })}
                </Card>
              )}
            </div>

            <div className="space-y-3">
              <h2 className="text-base font-bold text-ink">
                {t("dashboard.mostOftenWrong")}
              </h2>
              {metrics.questions_most_often_wrong.length === 0 ? (
                <Card>
                  <p className="text-sm text-inkMuted">
                    {t("dashboard.noWrongAnswers")}
                  </p>
                </Card>
              ) : (
                <Card className="py-2">
                  <ol className="divide-y divide-border">
                    {metrics.questions_most_often_wrong.map((question, index) => (
                      <li
                        className="grid grid-cols-[2rem_1fr_auto] items-start gap-2 py-3"
                        key={question.question_id}
                      >
                        <span className="grid h-7 w-7 place-items-center rounded-full bg-dangerTint text-sm font-bold text-dangerStrong">
                          {formatNumber(index + 1, locale)}
                        </span>
                        <span className="text-sm font-bold leading-5 text-ink">
                          {question.question[locale] ||
                            question.question[locales[0]]}
                        </span>
                        <span className="text-sm font-bold text-dangerStrong">
                          {t("dashboard.wrongCount", {
                            count: question.first_attempt_wrong_count,
                          })}
                        </span>
                      </li>
                    ))}
                  </ol>
                </Card>
              )}
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <ExclamationTriangleIcon className="h-5 w-5 text-warning" />
                <h2 className="text-base font-bold text-ink">
                  {t("dashboard.repeatHazards", {
                    days: metrics.repeat_hazard_window_days,
                    term: t("term.hazard"),
                  })}
                </h2>
              </div>
              {metrics.repeat_hazards.length === 0 ? (
                <Card>
                  <p className="text-sm text-inkMuted">
                    {t("dashboard.noRepeatHazards", {
                      days: metrics.repeat_hazard_window_days,
                      term: t("term.hazard"),
                    })}
                  </p>
                </Card>
              ) : (
                <div className="space-y-3">
                  {metrics.repeat_hazards.map((cluster) => (
                    <Card
                      className="space-y-3 border-warning"
                      key={`${cluster.category}:${cluster.location}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="font-bold text-ink">{cluster.category}</h3>
                          <p className="text-sm text-inkMuted">{cluster.location}</p>
                        </div>
                        <span className="rounded-chip bg-warningTint px-3 py-1 text-sm font-bold text-warning">
                          {t("dashboard.recurrenceCount", {
                            count: cluster.recurrence_count,
                          })}
                        </span>
                      </div>
                      <p className="text-sm text-inkMuted">
                        {t("dashboard.repeatHazardRange", {
                          reports: cluster.report_count,
                          first: formatDate(cluster.first_closed_at, locale),
                          latest: formatDate(cluster.latest_closed_at, locale),
                        })}
                      </p>
                      <div className="space-y-2 border-t border-border pt-3">
                        <div className="flex items-center gap-2 text-sm font-bold text-ink">
                          <UserGroupIcon className="h-5 w-5 text-inkMuted" />
                          <span>{t("dashboard.responsibleReworkProxy")}</span>
                        </div>
                        {cluster.responsible_rework.length === 0 ? (
                          <p className="text-sm text-inkMuted">
                            {t("dashboard.noResponsibleHistory")}
                          </p>
                        ) : (
                          <ul className="space-y-2">
                            {cluster.responsible_rework.map((responsible) => (
                              <li
                                className="flex items-center justify-between gap-3 text-sm"
                                key={responsible.profile_id}
                              >
                                <span className="min-w-0 font-bold text-ink">
                                  {responsible.display_name}
                                </span>
                                <span className="shrink-0 text-inkMuted">
                                  {t("dashboard.responsibleReworkValue", {
                                    rate: formatPercent(
                                      responsible.rework_rate,
                                      locale,
                                    ),
                                    count: responsible.action_count,
                                  })}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-3">
              <h2 className="text-base font-bold text-ink">
                {t("dashboard.openByStatus")}
              </h2>
              <Card className="divide-y divide-border py-1">
                {reportStatuses
                  .filter(
                    (status) => metrics.open_by_status[status] !== undefined,
                  )
                  .map((status) => (
                    <div
                      className="flex min-h-11 items-center justify-between gap-3 py-2"
                      key={status}
                    >
                      <StatusChip
                        status={status}
                        label={t(`status.${status}`)}
                      />
                      <span className="text-base font-bold text-ink">
                        {formatNumber(metrics.open_by_status[status] ?? 0, locale)}
                      </span>
                    </div>
                  ))}
              </Card>
            </div>

            <div className="space-y-3">
              <h2 className="text-base font-bold text-ink">
                {t("dashboard.workflowTimes")}
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <MetricCard
                  value={duration(
                    metrics.median_submitted_to_under_review_seconds,
                  )}
                  label={t("dashboard.toReview")}
                />
                <MetricCard
                  value={duration(
                    metrics.median_submitted_to_action_assigned_seconds,
                  )}
                  label={t("dashboard.toAssignment")}
                />
                <MetricCard
                  value={duration(
                    metrics.median_action_assigned_to_verified_closed_seconds,
                  )}
                  label={t("dashboard.assignmentToClose")}
                />
                <MetricCard
                  value={formatPercent(metrics.reviewer_correction_rate, locale)}
                  label={t("dashboard.correctionRate")}
                />
              </div>
            </div>
          </>
        ) : (
          <SecondaryButton label={t("dashboard.retry")} onClick={() => void load()} />
        )}
      </section>
    </AppShell>
  );
}
