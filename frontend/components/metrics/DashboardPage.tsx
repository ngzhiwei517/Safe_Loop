"use client";

import {
  BellIcon,
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  defaultLocale,
  formatDurationSeconds,
  formatNumber,
  formatPercent,
  isLocale,
  locales,
} from "../../lib/locales";
import { getMetricsSummary, type MetricsSummary } from "../../lib/metrics";
import { reportStatuses } from "../../lib/stateMachine";
import { createClient } from "../../lib/supabase/browser";
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

export function DashboardPage({ requestedLocale }: { requestedLocale: string }) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
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
  const navItems = [
    {
      href: `/${locale}/review`,
      label: t("review.nav.queue"),
      icon: <ClipboardDocumentListIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/actions`,
      label: t("review.nav.actions"),
      icon: <WrenchScrewdriverIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/documents`,
      label: t("review.nav.documents"),
      icon: <DocumentTextIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/briefings`,
      label: t("review.nav.briefings"),
      icon: <BookOpenIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/dashboard`,
      label: t("review.nav.dashboard"),
      icon: <ChartBarIcon className="h-5 w-5" />,
    },
  ];
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
