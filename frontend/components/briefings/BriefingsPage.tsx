"use client";

import {
  BellIcon,
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import { listManagedBriefings, type ManagedBriefing } from "../../lib/briefings";
import { defaultLocale, formatDate, isLocale, locales } from "../../lib/locales";
import { createClient } from "../../lib/supabase/browser";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { LanguageSwitch } from "../ui/LanguageSwitch";

const statusClasses = {
  draft: "bg-warningTint text-warning",
  published: "bg-successTint text-successStrong",
} as const;

export function BriefingsPage({ requestedLocale }: { requestedLocale: string }) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [briefings, setBriefings] = useState<ManagedBriefing[]>([]);
  const [loading, setLoading] = useState(true);
  const [failureKey, setFailureKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    setFailureKey(null);
    try {
      const { data: { session } } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      setBriefings(await listManagedBriefings(session.access_token));
    } catch (error) {
      setFailureKey(
        error instanceof ApiError && error.body.detail.code === "briefing_actor_forbidden"
          ? "error.briefing_actor_forbidden"
          : "briefings.error.generic",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const navItems = [
    { href: `/${locale}/review`, label: t("review.nav.queue"), icon: <ClipboardDocumentListIcon className="h-5 w-5" /> },
    { href: `/${locale}/actions`, label: t("review.nav.actions"), icon: <WrenchScrewdriverIcon className="h-5 w-5" /> },
    { href: `/${locale}/documents`, label: t("review.nav.documents"), icon: <DocumentTextIcon className="h-5 w-5" /> },
    { href: `/${locale}/briefings`, label: t("review.nav.briefings"), icon: <BookOpenIcon className="h-5 w-5" /> },
    { href: `/${locale}/dashboard`, label: t("review.nav.dashboard"), icon: <ChartBarIcon className="h-5 w-5" /> },
  ];

  return (
    <AppShell
      title={t("briefings.title")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={0}
      pollStatus
      showUrgentAlerts
      alertsHref={`/${locale}/alerts`}
      navItems={navItems}
      activeHref={`/${locale}/briefings`}
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
        <p className="text-sm leading-6 text-inkMuted">{t("briefings.intro")}</p>
        {failureKey && (
          <Banner tone="warning" title={t("briefings.error.title")} detail={t(failureKey)} />
        )}
        {loading ? (
          <p className="py-8 text-center text-base text-inkMuted" role="status">
            {t("briefings.loading")}
          </p>
        ) : briefings.length === 0 ? (
          <EmptyState
            icon={<BookOpenIcon className="h-8 w-8" />}
            title={t("briefings.empty.title")}
            detail={t("briefings.empty.detail")}
          />
        ) : (
          <div className="space-y-3">
            {briefings.map((briefing) => (
              <Card className="space-y-3" key={briefing.id}>
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <h2 className="text-lg font-bold text-ink">
                      {t("briefings.item.title", {
                        reference: briefing.human_ref,
                        version: briefing.version,
                      })}
                    </h2>
                    <p className="mt-1 text-sm text-inkMuted">
                      {briefing.target_activity || briefing.target_location
                        ? t("briefings.item.target", {
                            activity: briefing.target_activity ?? t("briefings.target.anyActivity"),
                            location: briefing.target_location ?? t("briefings.target.anyLocation"),
                          })
                        : t("briefings.item.noTarget")}
                    </p>
                  </div>
                  <span className={`rounded-chip px-3 py-1 text-xs font-bold ${statusClasses[briefing.status]}`}>
                    {t(`briefings.status.${briefing.status}`)}
                  </span>
                </div>
                <p className="line-clamp-3 whitespace-pre-line text-base leading-6 text-ink">
                  {briefing.body[locale] || briefing.body[locales[0]]}
                </p>
                <p className="text-sm text-inkMuted">
                  {briefing.approved_at
                    ? t("briefings.item.publishedAt", { date: formatDate(briefing.approved_at, locale) })
                    : t("briefings.item.createdAt", { date: formatDate(briefing.created_at, locale) })}
                </p>
                <Link
                  className="flex min-h-11 items-center justify-center rounded-control border border-border bg-surface px-4 text-base font-bold text-ink"
                  href={`/${locale}/briefings/${briefing.id}`}
                >
                  {t("briefings.item.open")}
                </Link>
              </Card>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
