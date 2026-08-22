"use client";

import { ArrowLeftIcon } from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import { defaultLocale, formatDateTime, isLocale } from "../../lib/locales";
import {
  getReport,
  getTimeline,
  transitionReport,
  type AvailableTransition,
  type ReportDetail as ReportDetailData,
  type TimelineEntry,
} from "../../lib/reports";
import type { ReportStatus } from "../../lib/stateMachine";
import { createClient } from "../../lib/supabase/browser";
import { Banner } from "../ui/Banner";
import { SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";
import { PhotoStrip } from "../ui/PhotoStrip";
import { StatusChip } from "../ui/StatusChip";
import { Timeline } from "../ui/Timeline";

const transitionErrorKeys: Record<string, string> = {
  reason_required: "error.reason_required",
  illegal_transition: "error.illegal_transition",
  terminal_state: "error.terminal_state",
  actor_not_permitted: "error.actor_not_permitted",
  role_not_permitted: "error.role_not_permitted",
  unknown_event: "error.unknown_event",
  database_guard: "error.database_guard",
};

function actorKey(entry: TimelineEntry): string {
  if (entry.actor_type === "human" && entry.actor_role) {
    return `timeline.actor.${entry.actor_role}`;
  }
  return `timeline.actor.${entry.actor_type}`;
}

export function ReportDetail({ id, requestedLocale }: { id: string; requestedLocale: string }) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [report, setReport] = useState<ReportDetailData | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [activeTransition, setActiveTransition] = useState<AvailableTransition | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionErrorKey, setActionErrorKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    const {
      data: { session },
    } = await createClient().auth.getSession();
    if (!session) throw new Error("session_required");
    const [nextReport, nextTimeline] = await Promise.all([
      getReport(id, session.access_token),
      getTimeline(id, session.access_token),
    ]);
    setReport(nextReport);
    setTimeline(nextTimeline);
  }, [id]);

  useEffect(() => {
    let active = true;
    async function initialLoad() {
      try {
        await load();
      } catch {
        if (active) setLoadFailed(true);
      } finally {
        if (active) setLoading(false);
      }
    }
    void initialLoad();
    return () => {
      active = false;
    };
  }, [load]);

  async function applyTransition(transition: AvailableTransition) {
    setSubmitting(true);
    setActionErrorKey(null);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      await transitionReport(
        id,
        transition.target,
        session.access_token,
        transition.requires_reason ? reason.trim() : undefined,
      );
      setActiveTransition(null);
      setReason("");
      await load();
    } catch (error) {
      const code = error instanceof ApiError ? error.body.detail.code : "";
      setActionErrorKey(transitionErrorKeys[code] ?? "report.detail.actionFailed");
    } finally {
      setSubmitting(false);
    }
  }

  function chooseTransition(transition: AvailableTransition) {
    setActionErrorKey(null);
    if (transition.requires_reason) {
      setActiveTransition(transition);
      setReason("");
      return;
    }
    void applyTransition(transition);
  }

  if (loading) {
    return <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 py-10 text-ink"><p className="text-base text-inkMuted" role="status">{t("report.detail.loading")}</p></main>;
  }

  if (loadFailed || report === null) {
    return <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 py-10 text-ink"><Banner tone="warning" title={t("report.detail.loadFailedTitle")} detail={t("report.detail.loadFailedDetail")} /></main>;
  }

  const timelineEvents = timeline.map((entry) => ({
    id: entry.id,
    title: t(`timeline.event.${entry.event}`),
    detail: t("timeline.actorAt", {
      actor: t(actorKey(entry)),
      time: formatDateTime(entry.created_at, locale),
    }),
    note: entry.reason ? t("timeline.reason", { reason: entry.reason }) : undefined,
    status: entry.target ?? undefined,
  }));

  return (
    <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 pb-10 text-ink">
      <header className="grid grid-cols-[44px_1fr_44px] items-center py-5">
        <Link className="grid min-h-11 min-w-11 place-items-center rounded-control" href={`/${locale}`} aria-label={t("report.detail.back")}>
          <ArrowLeftIcon className="h-7 w-7" />
        </Link>
        <h1 className="text-center text-xl font-bold">{t("report.detail.title")}</h1>
        <span />
      </header>

      <div className="space-y-4">
        <Card className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm text-inkMuted">{t("report.detail.reference")}</p>
              <p className="text-xl font-bold">{report.human_ref}</p>
            </div>
            <StatusChip status={report.status} label={t(`status.${report.status}`)} />
          </div>
          <p className="text-sm text-inkMuted">
            {t("report.detail.createdAt", { time: formatDateTime(report.created_at, locale) })}
          </p>
        </Card>

        {report.media.length > 0 && (
          <Card className="space-y-3">
            <h2 className="text-xl font-bold">{t("report.media.photos")}</h2>
            <PhotoStrip
              photos={report.media.map((item) => ({
                src: item.signed_url,
                alt: item.caption?.trim() || t("report.media.photoAlt"),
              }))}
            />
          </Card>
        )}

        <Card className="space-y-4">
          <section>
            <h2 className="text-xl font-bold">{t("report.detail.originalText")}</h2>
            <p className="mt-2 whitespace-pre-wrap text-base leading-7">{report.description_original}</p>
            <p className="mt-2 text-sm text-inkMuted">{t("report.detail.originalLanguage", { language: t(`locale.${report.lang_original}`) })}</p>
          </section>
          {report.description_en?.trim() && (
            <section className="border-t border-border pt-4">
              <h2 className="text-xl font-bold">{t("report.detail.englishText")}</h2>
              <p className="mt-2 whitespace-pre-wrap text-base leading-7">{report.description_en}</p>
            </section>
          )}
          {(report.location_text || report.activity || report.level_or_zone || report.grid_ref) && (
            <dl className="grid gap-3 border-t border-border pt-4 text-base">
              {report.location_text && <div><dt className="text-sm font-bold text-inkMuted">{t("report.detail.location")}</dt><dd>{report.location_text}</dd></div>}
              {report.activity && <div><dt className="text-sm font-bold text-inkMuted">{t("report.detail.activity")}</dt><dd>{report.activity}</dd></div>}
              {report.level_or_zone && <div><dt className="text-sm font-bold text-inkMuted">{t("report.detail.levelOrZone")}</dt><dd>{report.level_or_zone}</dd></div>}
              {report.grid_ref && <div><dt className="text-sm font-bold text-inkMuted">{t("report.detail.gridRef")}</dt><dd>{report.grid_ref}</dd></div>}
            </dl>
          )}
        </Card>

        <Card className="space-y-4">
          <h2 className="text-xl font-bold">{t("report.detail.timeline")}</h2>
          {timelineEvents.length > 0 ? <Timeline events={timelineEvents} /> : <p className="text-base text-inkMuted">{t("timeline.empty")}</p>}
        </Card>

        {actionErrorKey && <Banner tone="warning" title={t("report.detail.actionFailedTitle")} detail={t(actionErrorKey)} />}

        {report.available_transitions.length > 0 ? (
          <Card className="space-y-3">
            <h2 className="text-xl font-bold">{t("report.detail.actions")}</h2>
            {report.available_transitions.map((transition) => (
              <div className="space-y-3" key={transition.target}>
                {activeTransition?.target === transition.target ? (
                  <>
                    <Field
                      rows={3}
                      label={t("report.detail.reason")}
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                    />
                    <SecondaryButton
                      label={t(`action.${transition.event}`)}
                      disabled={reason.trim().length === 0 || submitting}
                      onClick={() => void applyTransition(transition)}
                    />
                  </>
                ) : (
                  <SecondaryButton
                    label={t(`action.${transition.event}`)}
                    disabled={submitting}
                    onClick={() => chooseTransition(transition)}
                  />
                )}
              </div>
            ))}
          </Card>
        ) : (
          <Banner
            tone="info"
            title={t("report.detail.waitingTitle")}
            detail={t(`report.detail.waiting.${report.status}`)}
          />
        )}
      </div>
    </main>
  );
}
