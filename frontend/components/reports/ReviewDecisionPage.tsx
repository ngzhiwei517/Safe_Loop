"use client";

import { ArrowLeftIcon } from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import {
  defaultLocale,
  formatDateTime,
  isLocale,
  locales,
} from "../../lib/locales";
import {
  getReport,
  getTimeline,
  reviewReport,
  urgencyLevels,
  type AvailableTransition,
  type ReportDetail,
  type ReviewDecision,
  type TimelineEntry,
  type Urgency,
} from "../../lib/reports";
import { createClient } from "../../lib/supabase/browser";
import { Banner } from "../ui/Banner";
import {
  DestructiveButton,
  PrimaryButton,
  SecondaryButton,
} from "../ui/Buttons";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { PhotoStrip } from "../ui/PhotoStrip";
import { StatusChip } from "../ui/StatusChip";
import { Timeline } from "../ui/Timeline";

type ReviewTransition = AvailableTransition & { review_decision: ReviewDecision };

const reviewErrorKeys: Record<string, string> = {
  reason_required: "error.reason_required",
  illegal_transition: "error.illegal_transition",
  terminal_state: "error.terminal_state",
  actor_not_permitted: "error.actor_not_permitted",
  role_not_permitted: "error.role_not_permitted",
  database_guard: "error.database_guard",
  assignment_required: "error.assignment_required",
  correction_reason_required: "error.correction_reason_required",
  review_target_mismatch: "error.review_target_mismatch",
  review_correction_invalid: "error.review_correction_invalid",
  review_actor_not_permitted: "error.review_actor_not_permitted",
  due_at_invalid: "error.due_at_invalid",
  assignee_not_responsible: "error.assignee_not_responsible",
  active_assignment_exists: "error.active_assignment_exists",
  report_not_found: "error.report_not_found",
};

function isReviewTransition(
  transition: AvailableTransition,
): transition is ReviewTransition {
  return transition.review_decision !== undefined;
}

function actorKey(entry: TimelineEntry): string {
  if (entry.actor_type === "human" && entry.actor_role) {
    return `timeline.actor.${entry.actor_role}`;
  }
  return `timeline.actor.${entry.actor_type}`;
}

function DecisionButton({
  decision,
  label,
  disabled,
  onClick,
  type = "button",
}: {
  decision: ReviewDecision;
  label: string;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  const props = { disabled, label, onClick, type };
  if (decision === "approve") return <PrimaryButton {...props} />;
  if (decision === "reject") return <DestructiveButton {...props} />;
  return <SecondaryButton {...props} />;
}

export function ReviewDecisionPage({
  id,
  requestedLocale,
}: {
  id: string;
  requestedLocale: string;
}) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [active, setActive] = useState<ReviewTransition | null>(null);
  const [reason, setReason] = useState("");
  const [correctedCategory, setCorrectedCategory] = useState("");
  const [correctedUrgency, setCorrectedUrgency] = useState<Urgency | "">("");
  const [correctedAction, setCorrectedAction] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
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
    let mounted = true;
    async function initialLoad() {
      try {
        await load();
      } catch {
        if (mounted) setLoadFailed(true);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void initialLoad();
    return () => {
      mounted = false;
    };
  }, [load]);

  function choose(transition: ReviewTransition) {
    setActive(transition);
    setReason("");
    setCorrectedCategory("");
    setCorrectedUrgency("");
    setCorrectedAction("");
    setCorrectionReason("");
    setAssigneeId("");
    setDueAt("");
    setErrorKey(null);
    setSaved(false);
  }

  const hasCorrections = Boolean(
    correctedCategory.trim() || correctedUrgency || correctedAction.trim(),
  );
  const reasonReady = !active?.requires_reason || reason.trim().length > 0;
  const correctionReady = !hasCorrections || correctionReason.trim().length > 0;
  const assignmentReady =
    active?.review_decision !== "approve" ||
    Boolean(
      correctedAction.trim() &&
        correctionReason.trim() &&
        assigneeId.trim() &&
        dueAt,
    );
  const ready = Boolean(active && reasonReady && correctionReady && assignmentReady);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!active || !ready) return;
    setSubmitting(true);
    setErrorKey(null);
    setSaved(false);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      const dueAtIso = dueAt ? new Date(dueAt).toISOString() : undefined;
      await reviewReport(
        id,
        {
          decision: active.review_decision,
          target: active.target,
          reason: active.requires_reason ? reason.trim() : undefined,
          corrected_category: correctedCategory.trim() || undefined,
          corrected_urgency: correctedUrgency || undefined,
          corrected_action: correctedAction.trim() || undefined,
          correction_reason: hasCorrections
            ? correctionReason.trim()
            : undefined,
          assignee_id:
            active.review_decision === "approve"
              ? assigneeId.trim()
              : undefined,
          due_at:
            active.review_decision === "approve" ? dueAtIso : undefined,
        },
        session.access_token,
      );
      setActive(null);
      setSaved(true);
      await load();
    } catch (error) {
      const code = error instanceof ApiError ? error.body.detail.code : "";
      setErrorKey(reviewErrorKeys[code] ?? "review.detail.submitFailedDetail");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 py-10 text-ink">
        <p className="text-base text-inkMuted" role="status">
          {t("review.detail.loading")}
        </p>
      </main>
    );
  }

  if (loadFailed || report === null) {
    return (
      <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 py-10 text-ink">
        <Banner
          tone="warning"
          title={t("review.detail.loadFailedTitle")}
          detail={t("review.detail.loadFailedDetail")}
        />
      </main>
    );
  }

  const decisions = report.available_transitions.filter(isReviewTransition);
  const timelineEvents = timeline.map((entry) => ({
    id: entry.id,
    title: t(`timeline.event.${entry.event}`),
    detail: t("timeline.actorAt", {
      actor: t(actorKey(entry)),
      time: formatDateTime(entry.created_at, locale),
    }),
    note: entry.reason
      ? t("timeline.reason", { reason: entry.reason })
      : undefined,
    status: entry.target ?? undefined,
  }));

  return (
    <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 pb-10 text-ink">
      <header className="grid grid-cols-[44px_1fr_auto] items-center gap-2 py-5">
        <Link
          className="grid min-h-11 min-w-11 place-items-center rounded-control"
          href={`/${locale}/review`}
          aria-label={t("review.detail.back")}
        >
          <ArrowLeftIcon className="h-7 w-7" />
        </Link>
        <h1 className="min-w-0 truncate text-center text-xl font-bold">
          {report.human_ref}
        </h1>
        <LanguageSwitch
          current={locale}
          label={t("app.language")}
          options={[
            { value: locales[0], label: t("app.languageEnglish") },
            { value: locales[1], label: t("app.languageChinese") },
          ]}
        />
      </header>

      <div className="space-y-4">
        <Card className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-bold text-inkMuted">
                {t("review.detail.report")}
              </p>
              <p className="mt-1 text-sm text-inkMuted">
                {t("report.detail.createdAt", {
                  time: formatDateTime(report.created_at, locale),
                })}
              </p>
            </div>
            <StatusChip
              status={report.status}
              label={t(`status.${report.status}`)}
            />
          </div>
          <p className="text-sm font-bold text-primaryStrong">
            {t("review.detail.urgency", {
              urgency: t(`urgency.${report.urgency}`),
            })}
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
            <h2 className="text-xl font-bold">
              {t("report.detail.originalText")}
            </h2>
            <p className="mt-2 whitespace-pre-wrap text-base leading-7">
              {report.description_original}
            </p>
            <p className="mt-2 text-sm text-inkMuted">
              {t("report.detail.originalLanguage", {
                language: t(`locale.${report.lang_original}`),
              })}
            </p>
          </section>
          {report.description_en?.trim() && (
            <section className="border-t border-border pt-4">
              <h2 className="text-xl font-bold">
                {t("report.detail.englishText")}
              </h2>
              <p className="mt-2 whitespace-pre-wrap text-base leading-7">
                {report.description_en}
              </p>
            </section>
          )}
          <dl className="grid gap-3 border-t border-border pt-4 text-base">
            {report.location_text && (
              <div>
                <dt className="text-sm font-bold text-inkMuted">
                  {t("report.detail.location")}
                </dt>
                <dd>{report.location_text}</dd>
              </div>
            )}
            {report.activity && (
              <div>
                <dt className="text-sm font-bold text-inkMuted">
                  {t("report.detail.activity")}
                </dt>
                <dd>{report.activity}</dd>
              </div>
            )}
            {report.level_or_zone && (
              <div>
                <dt className="text-sm font-bold text-inkMuted">
                  {t("report.detail.levelOrZone")}
                </dt>
                <dd>{report.level_or_zone}</dd>
              </div>
            )}
            {report.grid_ref && (
              <div>
                <dt className="text-sm font-bold text-inkMuted">
                  {t("report.detail.gridRef")}
                </dt>
                <dd>{report.grid_ref}</dd>
              </div>
            )}
          </dl>
        </Card>

        <Card className="space-y-4">
          <h2 className="text-xl font-bold">{t("report.detail.timeline")}</h2>
          {timelineEvents.length > 0 ? (
            <Timeline events={timelineEvents} />
          ) : (
            <p className="text-base text-inkMuted">{t("timeline.empty")}</p>
          )}
        </Card>

        {saved && (
          <Banner
            tone="info"
            title={t("review.detail.savedTitle")}
            detail={t("review.detail.savedDetail")}
          />
        )}
        {errorKey && (
          <Banner
            tone="warning"
            title={t("review.detail.submitFailedTitle")}
            detail={t(errorKey)}
          />
        )}

        {decisions.length === 0 ? (
          <Banner
            tone="info"
            title={t("review.detail.noActionsTitle")}
            detail={t("review.detail.noActionsDetail")}
          />
        ) : active ? (
          <Card className="space-y-4">
            <div>
              <p className="text-sm font-bold text-primaryStrong">
                {t("review.detail.decision")}
              </p>
              <h2 className="mt-1 text-xl font-bold">
                {t(`action.${active.event}`)}
              </h2>
            </div>
            <form className="space-y-4" onSubmit={submit}>
              {active.requires_reason && (
                <Field
                  rows={3}
                  label={t("review.detail.reason")}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  error={
                    reason.length > 0 && reason.trim().length === 0
                      ? t("error.reason_required")
                      : undefined
                  }
                />
              )}

              <details className="rounded-control border border-border bg-surfaceSunken p-4">
                <summary className="min-h-11 cursor-pointer text-base font-bold">
                  {t("review.detail.corrections")}
                </summary>
                <div className="space-y-4 pt-3">
                  <Field
                    label={t("review.detail.correctedCategory")}
                    value={correctedCategory}
                    onChange={(event) => setCorrectedCategory(event.target.value)}
                  />
                  <label className="block text-sm font-bold text-inkMuted">
                    <span>{t("review.detail.correctedUrgency")}</span>
                    <select
                      className="mt-1 min-h-[52px] w-full rounded-control border border-border bg-surface px-4 text-base text-ink outline-none focus:border-primaryStrong focus:ring-2 focus:ring-primaryTint"
                      value={correctedUrgency}
                      onChange={(event) =>
                        setCorrectedUrgency(event.target.value as Urgency | "")
                      }
                    >
                      <option value="">{t("review.detail.noCorrection")}</option>
                      {urgencyLevels.map((urgency) => (
                        <option key={urgency} value={urgency}>
                          {t(`urgency.${urgency}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Field
                    rows={3}
                    label={t("review.detail.correctedAction")}
                    value={correctedAction}
                    onChange={(event) => setCorrectedAction(event.target.value)}
                  />
                  {hasCorrections && (
                    <Field
                      rows={3}
                      label={t("review.detail.correctionReason")}
                      value={correctionReason}
                      onChange={(event) => setCorrectionReason(event.target.value)}
                      error={
                        correctionReason.length > 0 &&
                        correctionReason.trim().length === 0
                          ? t("error.correction_reason_required")
                          : undefined
                      }
                    />
                  )}
                </div>
              </details>

              {active.review_decision === "approve" && (
                <div className="space-y-4 rounded-control border border-border bg-successSurface p-4">
                  <p className="text-base font-bold text-successStrong">
                    {t("review.detail.assignment")}
                  </p>
                  <p className="text-sm text-inkMuted">
                    {t("review.detail.assignmentHelp")}
                  </p>
                  <Field
                    label={t("review.detail.assigneeId")}
                    value={assigneeId}
                    onChange={(event) => setAssigneeId(event.target.value)}
                  />
                  <Field
                    label={t("review.detail.dueAt")}
                    type="datetime-local"
                    value={dueAt}
                    onChange={(event) => setDueAt(event.target.value)}
                  />
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <SecondaryButton
                  className="min-h-14"
                  label={t("review.detail.cancel")}
                  disabled={submitting}
                  onClick={() => setActive(null)}
                  type="button"
                />
                <DecisionButton
                  decision={active.review_decision}
                  label={
                    submitting
                      ? t("review.detail.submitting")
                      : t(`action.${active.event}`)
                  }
                  disabled={!ready || submitting}
                  type="submit"
                />
              </div>
            </form>
          </Card>
        ) : (
          <Card className="space-y-3">
            <div>
              <h2 className="text-xl font-bold">
                {t("review.detail.actions")}
              </h2>
              <p className="mt-1 text-sm text-inkMuted">
                {t("review.detail.actionsHelp")}
              </p>
            </div>
            {decisions.map((transition) => (
              <DecisionButton
                decision={transition.review_decision}
                key={transition.event}
                label={t(`action.${transition.event}`)}
                onClick={() => choose(transition)}
              />
            ))}
          </Card>
        )}
      </div>
    </main>
  );
}
