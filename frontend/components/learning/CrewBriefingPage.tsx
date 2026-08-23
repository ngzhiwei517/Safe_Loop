"use client";

import {
  BookOpenIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { useState } from "react";

import {
  submitQuizAnswer,
  type PublicBriefing,
  type QuizAnswerResult,
} from "../../lib/briefings";
import { defaultLocale, formatDate, isLocale, locales } from "../../lib/locales";
import { createClient } from "../../lib/supabase/browser";
import { Card } from "../ui/Card";
import { LanguageSwitch } from "../ui/LanguageSwitch";

type AnswerState = QuizAnswerResult & { selectedOption: number };

export function briefingSections(body: string): string[] {
  const markdownSections = body
    .split(/\n(?=##\s+)/u)
    .map((section) => section.replace(/^##\s+[^\n]*\n?/u, "").trim())
    .filter(Boolean);
  if (markdownSections.length >= 3) {
    return [markdownSections[0], markdownSections[1], markdownSections.slice(2).join("\n\n")];
  }
  const paragraphs = body.split(/\n\s*\n/u).map((part) => part.trim()).filter(Boolean);
  return [paragraphs[0] ?? "", paragraphs[1] ?? "", paragraphs.slice(2).join("\n\n")];
}

export function CrewBriefingPage({
  requestedLocale,
  token,
  briefing,
  loadUnavailable = false,
}: {
  requestedLocale: string;
  token: string;
  briefing: PublicBriefing | null;
  loadUnavailable?: boolean;
}) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [failureKey, setFailureKey] = useState<string | null>(null);
  const sections = briefing
    ? briefingSections(briefing.body[locale] || briefing.body[locales[0]])
    : [];
  const sectionKeys = [
    "crew.section.whatHappened",
    "crew.section.whyMatters",
    "crew.section.doDifferently",
  ] as const;

  async function answer(questionId: string, selectedOption: number) {
    if (answers[questionId] || pendingQuestion) return;
    setFailureKey(null);
    setPendingQuestion(questionId);
    try {
      const { data: { session } } = await createClient().auth.getSession();
      const result = await submitQuizAnswer(
        token,
        questionId,
        selectedOption,
        session?.access_token,
      );
      setAnswers((current) => ({
        ...current,
        [questionId]: { ...result, selectedOption },
      }));
    } catch (error) {
      const code = error instanceof Error && "body" in error
        ? (error as { body?: { detail?: { code?: string } } }).body?.detail?.code
        : undefined;
      setFailureKey(
        code === "quiz_rate_limited"
          ? "crew.quiz.rateLimited"
          : "crew.quiz.failed",
      );
    } finally {
      setPendingQuestion(null);
    }
  }

  return (
    <div className="mx-auto min-h-screen max-w-[430px] bg-bg">
      <header className="flex items-center gap-3 border-b border-border px-5 py-4">
        <span className="grid h-11 w-11 place-items-center rounded-control bg-primaryTint text-primary">
          <BookOpenIcon className="h-6 w-6" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold uppercase tracking-wide text-inkMuted">
            {t("crew.kicker")}
          </p>
          <h1 className="text-xl font-bold text-ink">
            {t("crew.title", { term: t("term.toolboxBriefing") })}
          </h1>
        </div>
        <LanguageSwitch
          current={locale}
          label={t("app.language")}
          options={[
            { value: locales[0], label: t("app.languageEnglish") },
            { value: locales[1], label: t("app.languageChinese") },
          ]}
          persistProfile={false}
        />
      </header>

      <main className="space-y-5 px-5 py-6">
        {!briefing ? (
          <Card className="space-y-3 text-center">
            <ExclamationCircleIcon className="mx-auto h-10 w-10 text-warning" />
            <h2 className="text-xl font-bold text-ink">
              {t(loadUnavailable ? "crew.unavailable.title" : "crew.inactive.title")}
            </h2>
            <p className="text-base leading-6 text-inkMuted">
              {t(loadUnavailable ? "crew.unavailable.detail" : "crew.inactive.detail")}
            </p>
          </Card>
        ) : (
          <>
            <section className="space-y-3" aria-label={t("crew.context.label")}>
              <div className="flex flex-wrap gap-2">
                {briefing.target_activity && (
                  <span className="rounded-chip bg-primaryTint px-3 py-2 text-sm font-bold text-primaryStrong">
                    {briefing.target_activity}
                  </span>
                )}
                {briefing.target_location && (
                  <span className="rounded-chip border border-border bg-surface px-3 py-2 text-sm font-bold text-inkMuted">
                    {briefing.target_location}
                  </span>
                )}
              </div>
              <p className="text-sm text-inkMuted">
                {t("crew.validUntil", { date: formatDate(briefing.valid_to, locale) })}
              </p>
            </section>

            <ol className="space-y-0">
              {sectionKeys.map((key, index) => (
                <li className="grid grid-cols-[2.75rem_1fr] gap-3" key={key}>
                  <div className="flex flex-col items-center">
                    <span className="grid h-11 w-11 place-items-center rounded-full bg-ink text-base font-bold text-ink-inverse">
                      {index + 1}
                    </span>
                    {index < sectionKeys.length - 1 && (
                      <span className="min-h-8 w-px flex-1 bg-border" />
                    )}
                  </div>
                  <Card className="mb-3 space-y-2">
                    <h2 className="text-lg font-bold text-ink">{t(key)}</h2>
                    <p className="whitespace-pre-line text-base leading-7 text-ink">
                      {sections[index] || t("crew.section.unavailable")}
                    </p>
                  </Card>
                </li>
              ))}
            </ol>

            <section className="space-y-4 border-t border-border pt-5">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-primary">
                  {t("crew.quiz.kicker")}
                </p>
                <h2 className="mt-1 text-xl font-bold text-ink">{t("crew.quiz.title")}</h2>
                <p className="mt-1 text-base leading-6 text-inkMuted">{t("crew.quiz.detail")}</p>
              </div>

              {briefing.quiz_questions.map((question) => {
                const result = answers[question.id];
                return (
                  <Card className="space-y-4" key={question.id}>
                    <p className="text-sm font-bold text-primary">
                      {t("crew.quiz.questionNumber", { position: question.position })}
                    </p>
                    <h3 className="text-lg font-bold leading-7 text-ink">
                      {question.question[locale] || question.question[locales[0]]}
                    </h3>
                    <div className="space-y-2">
                      {question.options.map((option, optionIndex) => {
                        const selected = result?.selectedOption === optionIndex;
                        const correct = result?.correct_option === optionIndex;
                        const stateClass = result
                          ? correct
                            ? "border-success bg-successTint text-successStrong"
                            : selected
                              ? "border-danger bg-dangerTint text-danger"
                              : "border-border bg-surface text-inkMuted"
                          : "border-border bg-surface text-ink";
                        return (
                          <button
                            className={`min-h-11 w-full rounded-control border px-4 py-3 text-left text-base font-bold ${stateClass}`}
                            disabled={Boolean(result) || pendingQuestion !== null}
                            key={`${question.id}-${optionIndex}`}
                            onClick={() => void answer(question.id, optionIndex)}
                            type="button"
                          >
                            {option[locale] || option[locales[0]]}
                          </button>
                        );
                      })}
                    </div>
                    {result && (
                      <div
                        className={`rounded-control p-4 ${result.is_correct ? "bg-successTint" : "bg-warningTint"}`}
                        aria-live="polite"
                      >
                        <div className="flex items-center gap-2">
                          {result.is_correct ? (
                            <CheckCircleIcon className="h-6 w-6 text-successStrong" />
                          ) : (
                            <ExclamationCircleIcon className="h-6 w-6 text-warning" />
                          )}
                          <p className="text-base font-bold text-ink">
                            {t(result.is_correct ? "crew.quiz.correct" : "crew.quiz.incorrect")}
                          </p>
                        </div>
                        <p className="mt-2 text-base leading-6 text-ink">
                          {question.explanation[locale] || question.explanation[locales[0]]}
                        </p>
                      </div>
                    )}
                  </Card>
                );
              })}
              {failureKey && (
                <p className="rounded-control bg-dangerTint p-4 text-base font-bold text-danger" role="alert">
                  {t(failureKey)}
                </p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
