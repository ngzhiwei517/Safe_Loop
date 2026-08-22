"use client";

import {
  BellIcon,
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  HomeIcon,
  IdentificationIcon,
  LightBulbIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { defaultLocale, formatDateTime, isLocale, locales } from "../../lib/locales";
import {
  listNotifications,
  markNotificationRead,
  type NotificationItem,
} from "../../lib/notifications";
import { createClient } from "../../lib/supabase/browser";
import { AppShell, type AppShellNavItem } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { LanguageSwitch } from "../ui/LanguageSwitch";

type AppRole = "reporter" | "reviewer" | "responsible" | "crew" | "admin";

function notificationHref(item: NotificationItem, locale: string): string {
  if (item.kind === "alert_raised") return `/${locale}/alerts`;
  if (item.kind === "briefing_published") return `/${locale}/learn`;
  if (["assigned", "sent_back", "overdue"].includes(item.kind)) {
    return `/${locale}/actions`;
  }
  return `/${locale}/report/${item.entity_id}`;
}

export function InboxPage({
  requestedLocale,
  role,
}: {
  requestedLocale: string;
  role: AppRole;
}) {
  const t = useTranslations();
  const router = useRouter();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const load = useCallback(async () => {
    setLoadFailed(false);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      const feed = await listNotifications(session.access_token);
      setItems(feed.items);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function open(item: NotificationItem) {
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      if (item.read_at === null) {
        await markNotificationRead(item.id, session.access_token);
      }
      router.push(notificationHref(item, locale));
    } catch {
      setLoadFailed(true);
    }
  }

  const reviewerNav: AppShellNavItem[] = [
    { href: `/${locale}/review`, label: t("review.nav.queue"), icon: <ClipboardDocumentListIcon className="h-5 w-5" /> },
    { href: `/${locale}/actions`, label: t("review.nav.actions"), icon: <WrenchScrewdriverIcon className="h-5 w-5" /> },
    { href: `/${locale}/briefings`, label: t("review.nav.briefings"), icon: <BookOpenIcon className="h-5 w-5" /> },
    { href: `/${locale}/dashboard`, label: t("review.nav.dashboard"), icon: <ChartBarIcon className="h-5 w-5" /> },
  ];
  const standardNav: AppShellNavItem[] = [
    { href: `/${locale}`, label: t("app.home"), icon: <HomeIcon className="h-5 w-5" /> },
    { href: `/${locale}/reports`, label: t("app.myReports"), icon: <ClipboardDocumentListIcon className="h-5 w-5" /> },
    { href: `/${locale}/learn`, label: t("app.learn"), icon: <LightBulbIcon className="h-5 w-5" /> },
    { href: `/${locale}/profile`, label: t("app.profile"), icon: <IdentificationIcon className="h-5 w-5" /> },
  ];
  const reviewerSurface = role === "reviewer" || role === "admin";

  return (
    <AppShell
      title={t("inbox.title")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={items.filter((item) => item.read_at === null).length}
      pollStatus
      showUrgentAlerts={reviewerSurface}
      alertsHref={`/${locale}/alerts`}
      navItems={reviewerSurface ? reviewerNav : standardNav}
      activeHref={`/${locale}/inbox`}
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
      <section className="space-y-3 pb-6 pt-3">
        {loadFailed && (
          <Banner
            tone="warning"
            title={t("inbox.loadFailedTitle")}
            detail={t("inbox.loadFailedDetail")}
          />
        )}
        {loading ? (
          <p className="py-8 text-center text-base text-inkMuted" role="status">
            {t("inbox.loading")}
          </p>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<BellIcon className="h-8 w-8" />}
            title={t("inbox.emptyTitle")}
            detail={t("inbox.emptyDetail")}
          />
        ) : (
          items.map((item) => (
            <button
              type="button"
              className="block min-h-11 w-full text-left"
              onClick={() => void open(item)}
              key={item.id}
            >
              <Card className={`space-y-2 ${item.kind === "sent_back" ? "border-l-4 border-l-danger" : ""} ${item.read_at === null ? "bg-primaryTint" : ""}`}>
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-base font-bold">{t(`notification.${item.kind}`)}</h2>
                  {item.read_at === null && (
                    <span className="rounded-chip bg-danger px-2 py-1 text-xs font-bold text-ink-inverse">
                      {t("inbox.unread")}
                    </span>
                  )}
                </div>
                <p className="text-sm text-inkMuted">
                  {formatDateTime(item.created_at, locale)}
                </p>
              </Card>
            </button>
          ))
        )}
      </section>
    </AppShell>
  );
}
