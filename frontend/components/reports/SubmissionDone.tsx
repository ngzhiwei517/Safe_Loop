"use client";

import { CheckCircleIcon } from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { reportStatus } from "../../lib/stateMachine";
import { Card } from "../ui/Card";
import { StatusChip } from "../ui/StatusChip";

export function SubmissionDone({ id, locale }: { id: string; locale: string }) {
  const t = useTranslations();
  const [reference, setReference] = useState(id);
  useEffect(() => { setReference(sessionStorage.getItem(`safeloop-report-${id}`) ?? id); }, [id]);
  return <main className="mx-auto min-h-screen max-w-[430px] bg-bg px-5 pb-8 text-ink"><header className="border-b border-border py-5 text-center"><h1 className="text-2xl font-bold">{t("report.done.title")}</h1></header><Card className="mt-12 space-y-6 py-10 text-center"><CheckCircleIcon className="mx-auto h-20 w-20 text-success" /><h2 className="text-3xl font-bold">{t("report.done.heading")}</h2><p className="text-base text-inkMuted">{t("report.done.detail")}</p><div className="flex items-center justify-between rounded-control border border-border p-4 text-left"><span><small className="block text-sm text-inkMuted">{t("report.done.reference")}</small><strong className="text-lg">{reference}</strong></span><StatusChip status={reportStatus.submitted} label={t("status.submitted")} /></div></Card><div className="mt-7 space-y-3"><Link className="flex min-h-14 items-center justify-center rounded-control bg-primary px-5 text-base font-bold text-ink-inverse" href={`/${locale}/report/${id}`}>{t("report.done.view")}</Link><Link className="flex min-h-11 items-center justify-center text-base font-bold text-ink" href={`/${locale}`}>{t("report.done.home")}</Link></div><p className="mt-16 rounded-control border border-border p-4 text-center text-base text-inkMuted">{t("report.done.saved")}</p></main>;
}
