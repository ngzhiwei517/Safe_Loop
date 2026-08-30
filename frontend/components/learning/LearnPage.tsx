"use client";

import {
  BellIcon,
  BookOpenIcon,
} from "@heroicons/react/24/outline";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { listLearningBriefings, type LearningBriefing } from "../../lib/briefings";
import type { AppRole } from "../../lib/auth";
import { defaultLocale, formatDate, isLocale, locales } from "../../lib/locales";
import { createClient } from "../../lib/supabase/browser";
import { useRoleNavigation } from "../navigation/useRoleNavigation";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { briefingSections } from "./CrewBriefingPage";

export function LearnPage({
  requestedLocale,
  role,
}: {
  requestedLocale: string;
  role: AppRole;
}) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const navItems = useRoleNavigation(locale, role);
  const [briefings, setBriefings] = useState<LearningBriefing[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      const { data: { session } } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      setBriefings(await listLearningBriefings(session.access_token));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const reviewerSurface = role === "reviewer" || role === "admin";

  return (
    <AppShell
      title={t("learn.title")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={0}
      pollStatus
      showUrgentAlerts={reviewerSurface}
      alertsHref={`/${locale}/alerts`}
      navItems={navItems}
      activeHref={`/${locale}/learn`}
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
      <section className="space-y-4 pb-6 pt-3">
        <p className="text-base leading-6 text-inkMuted">{t("learn.intro")}</p>
        {failed && (
          <Banner tone="warning" title={t("learn.error.title")} detail={t("learn.error.detail")} />
        )}
        {loading ? (
          <p className="py-8 text-center text-base text-inkMuted" role="status">
            {t("learn.loading")}
          </p>
        ) : briefings.length === 0 ? (
          <EmptyState
            icon={<BookOpenIcon className="h-8 w-8" />}
            title={t("learn.empty.title")}
            detail={t("learn.empty.detail")}
          />
        ) : (
          <div className="space-y-3">
            {briefings.map((briefing) => {
              const preview = briefingSections(
                briefing.body[locale] || briefing.body[locales[0]],
              )[0];
              return (
                <Card className="space-y-3" key={briefing.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    {briefing.target_match && (
                      <span className="rounded-chip bg-primaryTint px-3 py-1 text-xs font-bold text-primaryStrong">
                        {t("learn.item.forYou")}
                      </span>
                    )}
                    <span className={`rounded-chip px-3 py-1 text-xs font-bold ${briefing.quiz_answered ? "bg-successTint text-successStrong" : "bg-warningTint text-warning"}`}>
                      {briefing.quiz_answered
                        ? t("learn.item.answered")
                        : briefing.answered_count > 0
                          ? t("learn.item.progress", {
                              answered: briefing.answered_count,
                              total: briefing.question_count,
                            })
                          : t("learn.item.notAnswered")}
                    </span>
                  </div>
                  <h2 className="text-lg font-bold text-ink">
                    {t("learn.item.title", { version: briefing.version })}
                  </h2>
                  <p className="line-clamp-3 whitespace-pre-line text-base leading-6 text-ink">
                    {preview}
                  </p>
                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-inkMuted">
                    {briefing.target_activity && <span>{briefing.target_activity}</span>}
                    {briefing.target_location && <span>{briefing.target_location}</span>}
                    <span>{t("learn.item.published", { date: formatDate(briefing.approved_at, locale) })}</span>
                  </div>
                  <Link
                    className="flex min-h-11 items-center justify-center rounded-control border border-border bg-surface px-4 text-base font-bold text-ink"
                    href={`/${locale}/b/${briefing.qr_token}`}
                  >
                    {t("learn.item.open")}
                  </Link>
                </Card>
              );
            })}
          </div>
        )}
      </section>
    </AppShell>
  );
}
