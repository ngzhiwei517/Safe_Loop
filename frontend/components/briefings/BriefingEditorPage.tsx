"use client";

import { BellIcon } from "@heroicons/react/24/outline";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import {
  getManagedBriefing,
  publishManagedBriefing,
  saveManagedBriefing,
  type BriefingEditPayload,
  type LocaleText,
  type ManagedBriefing,
} from "../../lib/briefings";
import {
  defaultLocale,
  isLocale,
  locales,
  siteTimeZone,
  type Locale,
} from "../../lib/locales";
import { createClient } from "../../lib/supabase/browser";
import { useOperationsNavigation } from "../navigation/useOperationsNavigation";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { PrimaryButton, SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { QrNoticeboardPanel } from "./QrNoticeboardPanel";

const errorKeys: Record<string, string> = {
  briefing_actor_forbidden: "error.briefing_actor_forbidden",
  briefing_not_found: "error.briefing_not_found",
  briefing_not_draft: "error.briefing_not_draft",
  briefing_not_editable: "error.briefing_not_editable",
  briefing_publish_conflict: "error.briefing_publish_conflict",
  briefing_token_conflict: "error.briefing_token_conflict",
  briefing_report_state_invalid: "error.briefing_report_state_invalid",
  briefing_locale_invalid: "error.briefing_locale_invalid",
  briefing_english_required: "error.briefing_english_required",
  briefing_both_locales_required: "error.briefing_both_locales_required",
  briefing_quiz_invalid: "error.briefing_quiz_invalid",
  briefing_validity_invalid: "error.briefing_validity_invalid",
  briefing_validity_required: "error.briefing_validity_required",
  briefing_too_long: "error.briefing_too_long",
  illegal_transition: "error.illegal_transition",
  terminal_state: "error.terminal_state",
  role_not_permitted: "error.role_not_permitted",
  actor_not_permitted: "error.actor_not_permitted",
  database_guard: "error.database_guard",
};

function dateInputValue(value: string | null): string {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat(defaultLocale, {
    timeZone: siteTimeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function editable(briefing: ManagedBriefing): BriefingEditPayload {
  return {
    body: briefing.body,
    target_activity: briefing.target_activity,
    target_location: briefing.target_location,
    valid_from: dateInputValue(briefing.valid_from) || null,
    valid_to: dateInputValue(briefing.valid_to) || null,
    quiz_questions: (briefing.quiz_questions ?? []).map((question) => ({
      position: question.position,
      question: question.question,
      explanation: question.explanation,
      options: question.options,
      correct_option: question.correct_option,
    })),
  };
}

function languageKey(locale: Locale): "app.languageEnglish" | "app.languageChinese" {
  return locale === locales[0] ? "app.languageEnglish" : "app.languageChinese";
}

export function BriefingEditorPage({
  id,
  requestedLocale,
}: {
  id: string;
  requestedLocale: string;
}) {
  const t = useTranslations();
  const router = useRouter();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const navItems = useOperationsNavigation(locale);
  const [briefing, setBriefing] = useState<ManagedBriefing | null>(null);
  const [draft, setDraft] = useState<BriefingEditPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<"save" | "publish" | null>(null);
  const [failureKey, setFailureKey] = useState<string | null>(null);
  const [successKey, setSuccessKey] = useState<string | null>(null);

  const token = useCallback(async () => {
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) throw new Error("session_required");
    return session.access_token;
  }, []);

  const errorKey = useCallback((error: unknown) => {
    if (error instanceof ApiError) {
      return errorKeys[error.body.detail.code] ?? "briefings.error.generic";
    }
    return "briefings.error.generic";
  }, []);

  const load = useCallback(async () => {
    setFailureKey(null);
    try {
      const result = await getManagedBriefing(id, await token());
      setBriefing(result);
      setDraft(editable(result));
    } catch (error) {
      setFailureKey(errorKey(error));
    } finally {
      setLoading(false);
    }
  }, [errorKey, id, token]);

  useEffect(() => {
    void load();
  }, [load]);

  function updateLocaleMap(
    current: LocaleText,
    localeCode: Locale,
    value: string,
  ): LocaleText {
    return { ...current, [localeCode]: value };
  }

  function updateQuestion(
    position: number,
    updater: (question: BriefingEditPayload["quiz_questions"][number]) => BriefingEditPayload["quiz_questions"][number],
  ) {
    setDraft((current) => current && ({
      ...current,
      quiz_questions: current.quiz_questions.map((question) =>
        question.position === position ? updater(question) : question),
    }));
  }

  async function save(): Promise<ManagedBriefing | null> {
    if (!briefing || !draft) return null;
    const result = await saveManagedBriefing(briefing.id, draft, await token());
    setBriefing(result);
    setDraft(editable(result));
    if (result.id !== briefing.id) {
      router.replace(`/${locale}/briefings/${result.id}`);
    }
    return result;
  }

  async function performSave() {
    setSaving("save");
    setFailureKey(null);
    setSuccessKey(null);
    try {
      await save();
      setSuccessKey("briefings.editor.saved");
    } catch (error) {
      setFailureKey(errorKey(error));
    } finally {
      setSaving(null);
    }
  }

  async function performPublish() {
    setSaving("publish");
    setFailureKey(null);
    setSuccessKey(null);
    try {
      const saved = await save();
      if (!saved) return;
      const result = await publishManagedBriefing(saved.id, await token());
      setBriefing(result);
      setDraft(editable(result));
      setSuccessKey("briefings.editor.published");
    } catch (error) {
      setFailureKey(errorKey(error));
    } finally {
      setSaving(null);
    }
  }

  const publicationTransition = briefing?.available_transitions[0];

  return (
    <AppShell
      title={briefing
        ? t("briefings.editor.title", { reference: briefing.human_ref, version: briefing.version })
        : t("briefings.editor.loadingTitle")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={0}
      pollStatus
      showUrgentAlerts
      alertsHref={`/${locale}/alerts`}
      navItems={navItems}
      activeHref={`/${locale}/briefings`}
      wide
      languageSwitch={(
        <LanguageSwitch
          current={locale}
          label={t("app.language")}
          options={[
            { value: locales[0], label: t("app.languageEnglish") },
            { value: locales[1], label: t("app.languageChinese") },
          ]}
        />
      )}
    >
      <section className="space-y-4 pb-8 pt-3">
        {failureKey && (
          <Banner tone="warning" title={t("briefings.error.title")} detail={t(failureKey)} />
        )}
        {successKey && (
          <Banner tone="info" title={t("briefings.editor.successTitle")} detail={t(successKey)} />
        )}
        {loading ? (
          <p className="py-8 text-center text-base text-inkMuted" role="status">
            {t("briefings.loading")}
          </p>
        ) : briefing && draft ? (
          <>
            <Banner
              tone="info"
              title={t("briefings.editor.aiTitle")}
              detail={t("briefings.editor.aiDetail")}
            />
            <Card className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-bold text-ink">{t("briefings.editor.targeting")}</h2>
                  <p className="text-sm text-inkMuted">{t("briefings.editor.targetingHelp")}</p>
                </div>
                <span className={`rounded-chip px-3 py-1 text-xs font-bold ${briefing.status === "published" ? "bg-successTint text-successStrong" : "bg-warningTint text-warning"}`}>
                  {t(`briefings.status.${briefing.status}`)}
                </span>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field
                  label={t("briefings.editor.targetActivity")}
                  value={draft.target_activity ?? ""}
                  onChange={(event) => setDraft({ ...draft, target_activity: event.target.value || null })}
                />
                <Field
                  label={t("briefings.editor.targetLocation")}
                  value={draft.target_location ?? ""}
                  onChange={(event) => setDraft({ ...draft, target_location: event.target.value || null })}
                />
                <Field
                  label={t("briefings.editor.validFrom")}
                  type="date"
                  value={draft.valid_from ?? ""}
                  onChange={(event) => setDraft({ ...draft, valid_from: event.target.value || null })}
                />
                <Field
                  label={t("briefings.editor.validTo")}
                  type="date"
                  value={draft.valid_to ?? ""}
                  onChange={(event) => setDraft({ ...draft, valid_to: event.target.value || null })}
                />
              </div>
            </Card>

            <Card className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-ink">{t("briefings.editor.bodyTitle")}</h2>
                <p className="text-sm text-inkMuted">{t("briefings.editor.bodyHelp")}</p>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                {locales.map((localeCode) => (
                  <Field
                    key={localeCode}
                    label={t("briefings.editor.bodyLabel", { language: t(languageKey(localeCode)) })}
                    rows={18}
                    value={draft.body[localeCode]}
                    onChange={(event) => setDraft({
                      ...draft,
                      body: updateLocaleMap(draft.body, localeCode, event.target.value),
                    })}
                  />
                ))}
              </div>
            </Card>

            {draft.quiz_questions.map((question) => (
              <Card className="space-y-5" key={question.position}>
                <div>
                  <h2 className="text-xl font-bold text-ink">
                    {t("briefings.editor.questionTitle", { position: question.position })}
                  </h2>
                  <p className="text-sm text-inkMuted">{t("briefings.editor.questionHelp")}</p>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  {locales.map((localeCode) => (
                    <Field
                      key={localeCode}
                      label={t("briefings.editor.questionLabel", { language: t(languageKey(localeCode)) })}
                      rows={3}
                      value={question.question[localeCode]}
                      onChange={(event) => updateQuestion(question.position, (current) => ({
                        ...current,
                        question: updateLocaleMap(current.question, localeCode, event.target.value),
                      }))}
                    />
                  ))}
                </div>
                {question.options.map((option, optionIndex) => (
                  <div className="grid gap-4 lg:grid-cols-2" key={optionIndex}>
                    {locales.map((localeCode) => (
                      <Field
                        key={localeCode}
                        label={t("briefings.editor.optionLabel", {
                          option: optionIndex + 1,
                          language: t(languageKey(localeCode)),
                        })}
                        rows={2}
                        value={option[localeCode]}
                        onChange={(event) => updateQuestion(question.position, (current) => ({
                          ...current,
                          options: current.options.map((currentOption, currentIndex) =>
                            currentIndex === optionIndex
                              ? updateLocaleMap(currentOption, localeCode, event.target.value)
                              : currentOption),
                        }))}
                      />
                    ))}
                  </div>
                ))}
                <div className="grid gap-4 lg:grid-cols-2">
                  {locales.map((localeCode) => (
                    <Field
                      key={localeCode}
                      label={t("briefings.editor.explanationLabel", { language: t(languageKey(localeCode)) })}
                      rows={3}
                      value={question.explanation[localeCode]}
                      onChange={(event) => updateQuestion(question.position, (current) => ({
                        ...current,
                        explanation: updateLocaleMap(current.explanation, localeCode, event.target.value),
                      }))}
                    />
                  ))}
                </div>
                <label className="block text-sm font-bold text-inkMuted">
                  <span>{t("briefings.editor.correctOption")}</span>
                  <select
                    className="mt-1 min-h-[52px] w-full rounded-control border border-border bg-surface px-4 text-base text-ink outline-none focus:border-primaryStrong focus:ring-2 focus:ring-primaryTint"
                    value={question.correct_option}
                    onChange={(event) => updateQuestion(question.position, (current) => ({
                      ...current,
                      correct_option: Number(event.target.value),
                    }))}
                  >
                    {question.options.map((_, optionIndex) => (
                      <option key={optionIndex} value={optionIndex}>
                        {t("briefings.editor.correctOptionValue", { option: optionIndex + 1 })}
                      </option>
                    ))}
                  </select>
                </label>
              </Card>
            ))}

            <div className="grid gap-3 md:grid-cols-2">
              <SecondaryButton
                disabled={saving !== null}
                label={saving === "save"
                  ? t("briefings.editor.saving")
                  : briefing.status === "published"
                    ? t("briefings.editor.createDraft")
                    : t("briefings.editor.save")}
                onClick={() => void performSave()}
              />
              {publicationTransition && (
                <PrimaryButton
                  disabled={saving !== null}
                  label={saving === "publish" ? t("briefings.editor.publishing") : t("briefings.editor.publish")}
                  onClick={() => void performPublish()}
                />
              )}
            </div>

            {briefing.status === "published" && briefing.qr_token && (
              <QrNoticeboardPanel briefing={briefing} locale={locale} />
            )}
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
