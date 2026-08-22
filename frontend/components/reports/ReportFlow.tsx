"use client";

import {
  ArrowLeftIcon,
  CameraIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ExclamationTriangleIcon,
  PlusIcon,
  ShieldExclamationIcon,
} from "@heroicons/react/24/outline";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import React, { ChangeEvent, useEffect, useState } from "react";

import {
  defaultLocale,
  isLocale,
  locales,
  type Locale,
} from "../../lib/locales";
import { fileReport } from "../../lib/reports";
import { createClient } from "../../lib/supabase/browser";
import { Banner } from "../ui/Banner";
import { PrimaryButton, SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";

type FlowStep = "capture" | "question" | "review";
type DangerAnswer = "yes" | "no" | null;

export function ReportFlow() {
  const t = useTranslations();
  const router = useRouter();
  const requestedLocale = useLocale();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [step, setStep] = useState<FlowStep>("capture");
  const [description, setDescription] = useState("");
  const [langOriginal, setLangOriginal] = useState<Locale>(locale);
  const [location, setLocation] = useState("");
  const [activity, setActivity] = useState("");
  const [levelOrZone, setLevelOrZone] = useState("");
  const [gridRef, setGridRef] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [confidential, setConfidential] = useState(false);
  const [danger, setDanger] = useState<DangerAnswer>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!photo) {
      setPhotoUrl(null);
      return;
    }

    const url = URL.createObjectURL(photo);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  function selectPhoto(event: ChangeEvent<HTMLInputElement>) {
    setPhoto(event.target.files?.[0] ?? null);
  }

  async function submit() {
    setSubmitting(true);
    setFailed(false);

    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) {
        throw new Error("session_required");
      }

      const report = await fileReport(
        {
          description_original: description.trim(),
          lang_original: langOriginal,
          location_text: location.trim(),
          activity: activity.trim(),
          level_or_zone: levelOrZone.trim() || null,
          grid_ref: gridRef.trim() || null,
          is_confidential: confidential,
          input_mode: "typed",
        },
        session.access_token,
      );
      try {
        sessionStorage.setItem(
          `safeloop-report-${report.id}`,
          report.human_ref,
        );
      } catch {
        // The confirmation page falls back to the report ID when storage is blocked.
      }
      router.push(`/${locale}/report/${report.id}`);
    } catch {
      setFailed(true);
      setSubmitting(false);
    }
  }

  const stepNumber = step === "capture" ? 1 : step === "question" ? 2 : 3;
  const title =
    step === "capture"
      ? t("report.new.captureTitle")
      : step === "question"
        ? t("report.new.questionTitle")
        : t("report.new.reviewTitle");
  const canContinue = description.trim().length > 0;
  const canSubmit =
    description.trim().length > 0 &&
    location.trim().length > 0 &&
    activity.trim().length > 0;

  return (
    <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 pb-6 text-ink">
      <header className="grid grid-cols-[44px_1fr_64px] items-center py-5">
        <button
          type="button"
          className="grid min-h-11 min-w-11 place-items-center rounded-control"
          aria-label={t("report.new.back")}
          onClick={() =>
            step === "capture"
              ? router.back()
              : setStep(step === "review" ? "question" : "capture")
          }
        >
          <ArrowLeftIcon className="h-7 w-7" />
        </button>
        <h1 className="text-center text-xl font-bold">{title}</h1>
        <span className="text-right text-base font-bold">
          {t("report.new.step", { current: stepNumber, total: 3 })}
        </span>
      </header>

      {step === "capture" && (
        <div className="space-y-4">
          <Card className="space-y-5">
            <label className="grid min-h-[320px] cursor-pointer place-items-center rounded-card border border-dashed border-border bg-surfaceSunken text-center">
              <span className="flex w-full flex-col items-center gap-2">
                {photoUrl ? (
                  <img
                    src={photoUrl}
                    alt={t("report.new.changePhoto")}
                    className="h-48 w-full rounded-tile object-cover"
                  />
                ) : (
                  <CameraIcon className="h-16 w-16" />
                )}
                <strong className="text-xl">
                  {photo
                    ? t("report.new.changePhoto")
                    : t("report.new.addPhoto")}
                </strong>
                <span className="text-base text-inkMuted">
                  {t("report.new.photoSafe")}
                </span>
              </span>
              <input
                className="sr-only"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                onChange={selectPhoto}
              />
            </label>
            <Field
              rows={5}
              label={t("report.new.whatHappened")}
              placeholder={t("report.new.descriptionExample", {
                guardrail: t("term.guardrail"),
              })}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <label className="block text-sm font-bold text-inkMuted">
              <span>{t("report.new.reportLanguage")}</span>
              <select
                className="mt-1 min-h-[52px] w-full rounded-control border border-border bg-surface px-4 text-base text-ink"
                value={langOriginal}
                onChange={(event) =>
                  setLangOriginal(event.target.value as Locale)
                }
              >
                {locales.map((item) => (
                  <option key={item} value={item}>
                    {item === locales[0]
                      ? t("app.languageEnglish")
                      : t("app.languageChinese")}
                  </option>
                ))}
              </select>
            </label>
          </Card>
          <PrimaryButton
            label={t("report.new.continue")}
            disabled={!canContinue}
            onClick={() => setStep("question")}
          />
        </div>
      )}

      {step === "question" && (
        <div className="space-y-5">
          <div className="flex justify-center gap-2" aria-hidden="true">
            <span className="h-2.5 w-8 rounded-chip bg-primary" />
          </div>
          <p className="text-center text-base text-inkMuted">
            {t("report.new.questionCount", { count: 1 })}
          </p>
          <Card className="flex min-h-[500px] flex-col justify-center gap-5 py-10 text-center">
            <ShieldExclamationIcon className="mx-auto h-20 w-20 text-danger" />
            <h2 className="text-2xl font-bold">
              {t("report.new.dangerQuestion")}
            </h2>
            {(["yes", "no"] as const).map((answer) => (
              <button
                key={answer}
                type="button"
                className={`flex min-h-16 w-full items-center gap-3 rounded-control border px-4 text-left text-base font-bold focus:outline-none focus:ring-2 focus:ring-primaryStrong ${
                  danger === answer
                    ? "border-primary bg-primaryTint"
                    : "border-border bg-surface"
                }`}
                onClick={() => setDanger(answer)}
              >
                {answer === "yes" ? (
                  <ExclamationTriangleIcon className="h-7 w-7 shrink-0 text-danger" />
                ) : danger === answer ? (
                  <CheckCircleIcon className="h-7 w-7 shrink-0 text-primaryStrong" />
                ) : (
                  <span className="h-7 w-7 shrink-0" aria-hidden="true" />
                )}
                <span>
                  {t(
                    answer === "yes"
                      ? "report.new.dangerYes"
                      : "report.new.dangerNo",
                  )}
                </span>
              </button>
            ))}
          </Card>
          <PrimaryButton
            label={t("report.new.continue")}
            disabled={!danger}
            onClick={() => setStep("review")}
          />
        </div>
      )}

      {step === "review" && (
        <div className="space-y-4">
          {photoUrl && (
            <div className="flex gap-2.5">
              <img
                className="h-32 min-w-0 flex-[5] rounded-tile object-cover"
                src={photoUrl}
                alt={t("report.new.changePhoto")}
              />
              <button
                type="button"
                className="grid h-32 flex-[4] place-items-center rounded-tile border border-dashed border-border bg-surfaceSunken"
                onClick={() => setStep("capture")}
                aria-label={t("report.new.addPhoto")}
              >
                <PlusIcon className="h-8 w-8" />
              </button>
            </div>
          )}
          <Card className="space-y-4">
            <h2 className="text-2xl font-bold">
              {t("report.new.whatReported")}
            </h2>
            <Field
              rows={4}
              label={t("report.new.whatHappened")}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <Field
              label={t("report.new.location")}
              placeholder={t("report.new.locationPlaceholder")}
              value={location}
              onChange={(event) => setLocation(event.target.value)}
            />
            <Field
              label={t("report.new.activity")}
              placeholder={t("report.new.activityPlaceholder")}
              value={activity}
              onChange={(event) => setActivity(event.target.value)}
            />
            <button
              type="button"
              className="flex min-h-11 w-full items-center justify-between text-left text-base font-bold"
              onClick={() => setDetailsOpen((open) => !open)}
            >
              <span>
                {t("report.new.moreDetail")} {" "}
                <span className="font-normal text-inkMuted">
                  {t("report.new.optional")}
                </span>
              </span>
              <ChevronDownIcon
                className={`h-5 w-5 transition ${
                  detailsOpen ? "rotate-180" : ""
                }`}
              />
            </button>
            {detailsOpen && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label={t("report.new.levelOrZone")}
                  value={levelOrZone}
                  onChange={(event) => setLevelOrZone(event.target.value)}
                />
                <Field
                  label={t("report.new.gridRef")}
                  value={gridRef}
                  onChange={(event) => setGridRef(event.target.value)}
                />
              </div>
            )}
            <label className="flex min-h-11 items-center justify-between gap-4 text-base font-bold">
              <span>{t("report.new.confidential")}</span>
              <input
                type="checkbox"
                className="h-6 w-6 accent-primary"
                checked={confidential}
                onChange={(event) => setConfidential(event.target.checked)}
              />
            </label>
          </Card>
          {failed && (
            <Banner
              tone="warning"
              title={t("report.new.failureTitle")}
              detail={t("report.new.failureDetail")}
            />
          )}
          <PrimaryButton
            label={
              submitting
                ? t("report.new.submitting")
                : t("report.new.submit")
            }
            disabled={!canSubmit || submitting}
            onClick={() => void submit()}
          />
          {failed && (
            <SecondaryButton
              label={t("report.new.retry")}
              onClick={() => void submit()}
            />
          )}
        </div>
      )}
    </main>
  );
}
