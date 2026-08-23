"use client";

import { ArrowDownTrayIcon, QrCodeIcon } from "@heroicons/react/24/outline";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import {
  briefingPublicUrl,
  downloadNoticeboardPdf,
  downloadNoticeboardPng,
  qrDataUrl,
  type NoticeboardCopy,
} from "../../lib/briefingQr";
import type { ManagedBriefing } from "../../lib/briefings";
import { formatDate, type Locale } from "../../lib/locales";
import { Banner } from "../ui/Banner";
import { SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";

export function QrNoticeboardPanel({
  briefing,
  locale,
}: {
  briefing: ManagedBriefing;
  locale: Locale;
}) {
  const t = useTranslations();
  const [publicUrl, setPublicUrl] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"png" | "pdf" | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!briefing.qr_token) return;
    const url = briefingPublicUrl(window.location.origin, locale, briefing.qr_token);
    setPublicUrl(url);
    void qrDataUrl(url).then(setPreview).catch(() => setFailed(true));
  }, [briefing.qr_token, locale]);

  const copy = useMemo<NoticeboardCopy>(() => ({
    title: t("briefings.qr.sheetTitle", { term: t("term.toolboxBriefing") }),
    instruction: t("briefings.qr.instruction"),
    reference: t("briefings.qr.reference", {
      reference: briefing.human_ref,
      version: briefing.version,
    }),
    validity: briefing.valid_to
      ? t("briefings.qr.validTo", { date: formatDate(briefing.valid_to, locale) })
      : t("briefings.qr.noExpiry"),
    footer: t("briefings.qr.footer"),
  }), [briefing, locale, t]);

  const filename = t("briefings.qr.filename", {
    reference: briefing.human_ref,
    version: briefing.version,
  }).replace(/[^\p{L}\p{N}._-]+/gu, "-");

  async function download(kind: "png" | "pdf") {
    if (!publicUrl) return;
    setDownloading(kind);
    setFailed(false);
    try {
      if (kind === "png") {
        await downloadNoticeboardPng(publicUrl, copy, filename);
      } else {
        await downloadNoticeboardPdf(publicUrl, copy, filename);
      }
    } catch {
      setFailed(true);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <Card className="space-y-4 bg-successSurface">
      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-tile bg-successTint text-successStrong">
          <QrCodeIcon className="h-7 w-7" />
        </span>
        <div>
          <h2 className="text-xl font-bold text-ink">{t("briefings.qr.title")}</h2>
          <p className="text-sm text-inkMuted">{t("briefings.qr.detail")}</p>
        </div>
      </div>
      {failed && (
        <Banner tone="warning" title={t("briefings.error.title")} detail={t("briefings.qr.failed")} />
      )}
      <div className="mx-auto aspect-[210/297] w-full max-w-[360px] border border-border bg-surface p-8 shadow-safe">
        <div className="h-2 bg-primary" />
        <h3 className="mt-8 text-center text-2xl font-bold text-ink">{copy.title}</h3>
        <p className="mt-3 text-center text-base text-inkMuted">{copy.instruction}</p>
        {preview && (
          <Image
            alt={t("briefings.qr.alt")}
            className="mx-auto mt-8 aspect-square w-3/4"
            height={680}
            src={preview}
            unoptimized
            width={680}
          />
        )}
        <p className="mt-6 text-center text-sm font-bold text-ink">{copy.reference}</p>
        <p className="mt-2 text-center text-sm text-inkMuted">{copy.validity}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <SecondaryButton
          disabled={!preview || downloading !== null}
          label={downloading === "png" ? t("briefings.qr.preparing") : t("briefings.qr.downloadPng")}
          onClick={() => void download("png")}
        />
        <SecondaryButton
          disabled={!preview || downloading !== null}
          label={downloading === "pdf" ? t("briefings.qr.preparing") : t("briefings.qr.downloadPdf")}
          onClick={() => void download("pdf")}
        />
      </div>
      <p className="flex items-center justify-center gap-2 text-sm text-inkMuted">
        <ArrowDownTrayIcon className="h-4 w-4" />
        {t("briefings.qr.printHelp")}
      </p>
    </Card>
  );
}
