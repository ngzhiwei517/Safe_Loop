"use client";

import { CheckCircleIcon } from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getReport, type ReportMedia } from "../../lib/reports";
import { reportStatus, type ReportStatus } from "../../lib/stateMachine";
import { createClient } from "../../lib/supabase/browser";
import { Card } from "../ui/Card";
import { StatusChip } from "../ui/StatusChip";

export function SubmissionDone({ id, locale }: { id: string; locale: string }) {
  const t = useTranslations();
  const [reference, setReference] = useState(id);
  const [status, setStatus] = useState<ReportStatus>(reportStatus.submitted);
  const [media, setMedia] = useState<ReportMedia[]>([]);
  const [mediaFailed, setMediaFailed] = useState(false);

  useEffect(() => {
    let active = true;
    try {
      setReference(sessionStorage.getItem(`safeloop-report-${id}`) ?? id);
    } catch {
      setReference(id);
    }

    async function loadReport() {
      try {
        const {
          data: { session },
        } = await createClient().auth.getSession();
        if (!session) return;
        const report = await getReport(id, session.access_token);
        if (active) {
          setReference(report.human_ref);
          setStatus(report.status);
          setMedia(report.media);
        }
      } catch {
        if (active) setMediaFailed(true);
      }
    }

    void loadReport();
    return () => {
      active = false;
    };
  }, [id]);

  return (
    <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 pb-8 text-ink">
      <header className="border-b border-border py-5 text-center">
        <h1 className="text-2xl font-bold">{t("report.done.title")}</h1>
      </header>
      <Card className="mt-12 space-y-6 py-10 text-center">
        <CheckCircleIcon className="mx-auto h-20 w-20 text-success" />
        <h2 className="text-3xl font-bold">{t("report.done.heading")}</h2>
        <p className="text-base text-inkMuted">{t("report.done.detail")}</p>
        <div className="flex items-center justify-between rounded-control border border-border p-4 text-left">
          <span>
            <small className="block text-sm text-inkMuted">
              {t("report.done.reference")}
            </small>
            <strong className="text-lg">{reference}</strong>
          </span>
          <StatusChip status={status} label={t(`status.${status}`)} />
        </div>
        {media.length > 0 && (
          <section className="space-y-3 text-left">
            <h3 className="text-base font-bold">{t("report.media.photos")}</h3>
            <div className="grid grid-cols-2 gap-3">
              {media.map((item) => (
                <img
                  key={item.id}
                  className="h-36 w-full rounded-tile object-cover"
                  src={item.signed_url}
                  alt={item.caption?.trim() || t("report.media.photoAlt")}
                />
              ))}
            </div>
          </section>
        )}
        {mediaFailed && (
          <p className="text-sm text-warning" role="status">
            {t("report.media.loadFailed")}
          </p>
        )}
      </Card>
      <div className="mt-7 space-y-3">
        <Link
          className="flex min-h-14 items-center justify-center rounded-control bg-primary px-5 text-base font-bold text-ink-inverse"
          href={`/${locale}/report/${id}`}
        >
          {t("report.done.view")}
        </Link>
        <Link
          className="flex min-h-11 items-center justify-center text-base font-bold text-ink"
          href={`/${locale}`}
        >
          {t("report.done.home")}
        </Link>
      </div>
      <p className="mt-16 rounded-control border border-border p-4 text-center text-base text-inkMuted">
        {t("report.done.saved")}
      </p>
    </main>
  );
}
