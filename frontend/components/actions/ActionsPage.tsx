"use client";

import {
  ArrowLeftIcon,
  BellIcon,
  BookOpenIcon,
  CameraIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  MapPinIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { type ChangeEvent, useCallback, useEffect, useState } from "react";

import {
  isReturnedAction,
  listOpenActions,
  submitActionEvidence,
  type OpenAction,
} from "../../lib/actions";
import { ApiError } from "../../lib/api";
import {
  defaultLocale,
  formatDateTime,
  formatNumber,
  isLocale,
  locales,
} from "../../lib/locales";
import {
  mediaPhase,
  MediaUploadError,
  uploadReportPhoto,
} from "../../lib/media";
import { createClient } from "../../lib/supabase/browser";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { PrimaryButton, SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Field } from "../ui/Field";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { PhotoStrip } from "../ui/PhotoStrip";

const actionErrorKeys: Record<string, string> = {
  action_actor_forbidden: "error.action_actor_forbidden",
  action_forbidden: "error.action_forbidden",
  action_not_found: "error.action_not_found",
  action_not_submittable: "error.action_not_submittable",
  action_evidence_required: "error.action_evidence_required",
  action_media_invalid: "error.action_media_invalid",
  media_type_not_allowed: "error.media_type_not_allowed",
  media_too_large: "error.media_too_large",
  media_upload_failed: "error.media_upload_failed",
  media_downscale_failed: "error.media_downscale_failed",
};

function evidenceErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    return actionErrorKeys[error.body.detail.code] ?? "work.submit.failureDetail";
  }
  if (error instanceof MediaUploadError) {
    return actionErrorKeys[error.code] ?? "work.submit.failureDetail";
  }
  return "work.submit.failureDetail";
}

function ReturnedContext({
  action,
  photoAlt,
  title,
  reviewerLabel,
  evidenceLabel,
  missingReason,
}: {
  action: OpenAction;
  photoAlt: string;
  title: string;
  reviewerLabel: string;
  evidenceLabel: string;
  missingReason: string;
}) {
  const deficiency = action.deficiency_reason ?? action.deficiency_notes ?? missingReason;
  return (
    <section
      className="space-y-3 rounded-card border border-danger bg-dangerTint p-4"
      aria-label={title}
    >
      <div className="flex items-center gap-2 text-dangerStrong">
        <ExclamationTriangleIcon className="h-6 w-6 shrink-0" />
        <h2 className="text-base font-bold">{title}</h2>
      </div>
      <div className="rounded-control bg-surface p-4">
        <p className="text-xs font-bold uppercase tracking-wide text-inkMuted">
          {reviewerLabel}
        </p>
        <p className="mt-1 text-base font-bold text-ink">{deficiency}</p>
      </div>
      {action.completed_note && (
        <p className="text-sm text-inkMuted">{action.completed_note}</p>
      )}
      {action.previous_evidence.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-bold text-inkMuted">{evidenceLabel}</p>
          <PhotoStrip
            photos={action.previous_evidence
              .filter((evidence) => evidence.signed_url)
              .map((evidence) => ({
                src: evidence.signed_url!,
                alt: evidence.caption?.trim() || photoAlt,
              }))}
          />
        </div>
      )}
    </section>
  );
}

export function ActionsPage({ requestedLocale }: { requestedLocale: string }) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [actions, setActions] = useState<OpenAction[]>([]);
  const [selected, setSelected] = useState<OpenAction | null>(null);
  const [completedNote, setCompletedNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const [registeredMediaIds, setRegisteredMediaIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [failureKey, setFailureKey] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const load = useCallback(async () => {
    setFailureKey(null);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      setActions(await listOpenActions(session.access_token));
    } catch {
      setFailureKey("action.list.failureDetail");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(
    () => () => previewUrls.forEach((url) => URL.revokeObjectURL(url)),
    [previewUrls],
  );

  function choose(action: OpenAction) {
    previewUrls.forEach((url) => URL.revokeObjectURL(url));
    setSelected(action);
    setCompletedNote("");
    setFiles([]);
    setPreviewUrls([]);
    setRegisteredMediaIds([]);
    setFailureKey(null);
    setSubmitted(false);
  }

  function chooseFiles(event: ChangeEvent<HTMLInputElement>) {
    previewUrls.forEach((url) => URL.revokeObjectURL(url));
    const selectedFiles = Array.from(event.target.files ?? []).slice(0, 5);
    setFiles(selectedFiles);
    setPreviewUrls(selectedFiles.map((file) => URL.createObjectURL(file)));
    setRegisteredMediaIds([]);
    setFailureKey(null);
  }

  async function submit() {
    if (!selected) return;
    if (!completedNote.trim() && files.length === 0) {
      setFailureKey("error.action_evidence_required");
      return;
    }
    setSubmitting(true);
    setFailureKey(null);
    const client = createClient();
    try {
      const {
        data: { session },
      } = await client.auth.getSession();
      if (!session) throw new Error("session_required");
      const {
        data: { user },
      } = await client.auth.getUser();
      if (!user) throw new Error("session_required");

      const mediaIds = [...registeredMediaIds];
      for (const file of files.slice(mediaIds.length)) {
        const registered = await uploadReportPhoto({
          client,
          file,
          userId: user.id,
          reportId: selected.id,
          accessToken: session.access_token,
          caption: null,
          phase: mediaPhase.evidence,
        });
        mediaIds.push(registered.id);
        setRegisteredMediaIds([...mediaIds]);
      }
      await submitActionEvidence(
        selected.id,
        selected.action_id,
        {
          completed_note: completedNote.trim() || undefined,
          media_ids: mediaIds,
        },
        session.access_token,
      );
      setSelected(null);
      setCompletedNote("");
      setFiles([]);
      setPreviewUrls([]);
      setRegisteredMediaIds([]);
      setSubmitted(true);
      await load();
    } catch (error) {
      setFailureKey(evidenceErrorKey(error));
    } finally {
      setSubmitting(false);
    }
  }

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
      href: `/${locale}/actions`,
      label: t("action.nav.myWork"),
      icon: <WrenchScrewdriverIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/learn`,
      label: t("app.learn"),
      icon: <BookOpenIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/profile`,
      label: t("app.profile"),
      icon: <IdentificationIcon className="h-5 w-5" />,
    },
  ];

  const returnedContextProps = selected
    ? {
        action: selected,
        photoAlt: t("action.previous.photoAlt"),
        title: t("action.returned.title"),
        reviewerLabel: t("action.returned.reviewer", {
          name: selected.deficiency_reviewer_name ?? t("action.returned.reviewerUnknown"),
        }),
        evidenceLabel: t("action.previous.evidence"),
        missingReason: t("action.returned.reasonMissing"),
      }
    : null;

  return (
    <AppShell
      title={selected ? t("work.submit.title") : t("action.list.title")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={0}
      pollStatus
      priorityBadgeLabel={(count) => t("action.returned.badge", { count })}
      navItems={navItems}
      activeHref={`/${locale}/actions`}
      languageSwitch={languageSwitch}
    >
      {selected ? (
        <section className="space-y-4 pb-6 pt-3">
          <button
            type="button"
            className="flex min-h-11 items-center gap-2 font-bold text-primaryStrong"
            onClick={() => setSelected(null)}
          >
            <ArrowLeftIcon className="h-5 w-5" />
            <span>{t("work.submit.back")}</span>
          </button>

          {isReturnedAction(selected) && returnedContextProps && (
            <ReturnedContext {...returnedContextProps} />
          )}

          <Card className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-wide text-primaryStrong">
              {selected.human_ref}
            </p>
            <h2 className="text-lg font-bold text-ink">{selected.action_text}</h2>
            <div className="flex items-center gap-2 text-sm text-inkMuted">
              <MapPinIcon className="h-5 w-5 shrink-0" />
              <span>{selected.location_text?.trim() || t("action.locationUnknown")}</span>
            </div>
            <p className="text-sm font-bold text-inkMuted">
              {t("action.due", {
                date: formatDateTime(selected.action_due_at, locale),
              })}
            </p>
          </Card>

          <div className="space-y-2">
            <p className="text-sm font-bold text-inkMuted">
              {t("work.submit.photos")}
            </p>
            {previewUrls.length > 0 && (
              <PhotoStrip
                photos={previewUrls.map((url, index) => ({
                  src: url,
                  alt: t("work.submit.photoAlt", {
                    number: formatNumber(index + 1, locale),
                  }),
                }))}
              />
            )}
            <label className="flex min-h-14 cursor-pointer items-center justify-center gap-2 rounded-control border border-dashed border-primaryStrong bg-primaryTint px-4 text-base font-bold text-primaryStrong focus-within:ring-2 focus-within:ring-primaryStrong">
              <CameraIcon className="h-6 w-6" />
              <span>
                {files.length > 0
                  ? t("work.submit.changePhotos")
                  : t("work.submit.addPhotos")}
              </span>
              <input
                className="sr-only"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                multiple
                onChange={chooseFiles}
              />
            </label>
          </div>

          <Field
            label={t("work.submit.note")}
            placeholder={t("work.submit.notePlaceholder")}
            rows={4}
            value={completedNote}
            onChange={(event) => setCompletedNote(event.target.value)}
          />

          <p className="text-sm text-inkMuted">{t("work.submit.requirement")}</p>
          {failureKey && (
            <Banner
              tone="warning"
              title={t("work.submit.failureTitle")}
              detail={t(failureKey)}
            />
          )}
          <PrimaryButton
            label={submitting ? t("work.submit.sending") : t("work.submit.send")}
            disabled={submitting || (!completedNote.trim() && files.length === 0)}
            onClick={() => void submit()}
          />
        </section>
      ) : (
        <section className="space-y-4 pb-6 pt-3">
          {submitted && (
            <Banner
              tone="info"
              title={t("work.submit.successTitle")}
              detail={t("work.submit.successDetail")}
            />
          )}
          {failureKey && (
            <Banner
              tone="warning"
              title={t("action.list.failureTitle")}
              detail={t(failureKey)}
            />
          )}
          {loading ? (
            <p className="py-8 text-center text-base text-inkMuted" role="status">
              {t("action.list.loading")}
            </p>
          ) : actions.length === 0 ? (
            <EmptyState
              icon={<CheckCircleIcon className="h-8 w-8" />}
              title={t("action.list.emptyTitle")}
              detail={t("action.list.emptyDetail")}
            />
          ) : (
            actions.map((action, index) => {
              const returned = isReturnedAction(action);
              const overdue = new Date(action.action_due_at).getTime() < Date.now();
              const contextProps = {
                action,
                photoAlt: t("action.previous.photoAlt"),
                title: t("action.returned.title"),
                reviewerLabel: t("action.returned.reviewer", {
                  name:
                    action.deficiency_reviewer_name ??
                    t("action.returned.reviewerUnknown"),
                }),
                evidenceLabel: t("action.previous.evidence"),
                missingReason: t("action.returned.reasonMissing"),
              };
              return (
                <Card
                  className={`space-y-4 ${returned ? "border-danger bg-dangerTint" : ""}`}
                  key={action.action_id}
                >
                  {returned && <ReturnedContext {...contextProps} />}
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-xs font-bold uppercase tracking-wide text-primaryStrong">
                        {action.human_ref}
                      </p>
                      <div className="flex flex-wrap justify-end gap-2">
                        {returned && (
                          <span className="rounded-chip bg-warning px-2 py-1 text-xs font-bold text-ink">
                            {t("action.returned.badgeShort")}
                          </span>
                        )}
                        {overdue && (
                          <span className="rounded-chip bg-danger px-2 py-1 text-xs font-bold text-ink-inverse">
                            {t("action.overdue")}
                          </span>
                        )}
                      </div>
                    </div>
                    <h2 className="text-lg font-bold text-ink">{action.action_text}</h2>
                    <p className="text-base text-inkMuted">{action.summary}</p>
                    <div className="flex items-center gap-2 text-sm text-inkMuted">
                      <MapPinIcon className="h-5 w-5 shrink-0" />
                      <span>
                        {action.location_text?.trim() || t("action.locationUnknown")}
                      </span>
                    </div>
                    <p className={`text-sm font-bold ${overdue ? "text-danger" : "text-inkMuted"}`}>
                      {t("action.due", {
                        date: formatDateTime(action.action_due_at, locale),
                      })}
                    </p>
                  </div>
                  {index === 0 ? (
                    <PrimaryButton
                      label={returned ? t("work.submit.again") : t("work.submit.open")}
                      onClick={() => choose(action)}
                    />
                  ) : (
                    <SecondaryButton
                      label={returned ? t("work.submit.again") : t("work.submit.open")}
                      onClick={() => choose(action)}
                    />
                  )}
                </Card>
              );
            })
          )}
        </section>
      )}
    </AppShell>
  );
}
