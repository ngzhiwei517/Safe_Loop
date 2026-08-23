"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useState } from "react";

import { listAlerts, type AlertItem } from "../../lib/alerts";
import { listNotifications } from "../../lib/notifications";
import { alertPollIntervalMs } from "../../lib/site";
import { createClient } from "../../lib/supabase/browser";
import { Banner } from "./Banner";

export type AppShellNavItem = { href: string; label: string; icon: ReactNode };

type IdentityHeader = {
  title?: never;
  greeting: string;
  name: string;
  avatar?: ReactNode;
};

type TitleHeader = {
  title: string;
  greeting?: never;
  name?: never;
  avatar?: never;
};

type AppShellProps = (IdentityHeader | TitleHeader) & {
  children: ReactNode;
  inboxHref: string;
  inboxLabel: string;
  inboxIcon?: ReactNode;
  unreadCount: number;
  navItems: AppShellNavItem[];
  activeHref: string;
  languageSwitch?: ReactNode;
  pollStatus?: boolean;
  showUrgentAlerts?: boolean;
  alertsHref?: string;
  priorityBadgeLabel?: (count: number) => string;
  wide?: boolean;
};

export function AppShell({
  children,
  title,
  greeting,
  name,
  avatar = null,
  inboxHref,
  inboxLabel,
  inboxIcon = null,
  unreadCount,
  navItems,
  activeHref,
  languageSwitch = null,
  pollStatus = false,
  showUrgentAlerts = false,
  alertsHref,
  priorityBadgeLabel,
  wide = false,
}: AppShellProps) {
  const t = useTranslations();
  const [liveUnreadCount, setLiveUnreadCount] = useState(unreadCount);
  const [unresolvedSentBackCount, setUnresolvedSentBackCount] = useState(0);
  const [urgentAlert, setUrgentAlert] = useState<AlertItem | null>(null);

  useEffect(() => {
    if (!pollStatus) return;
    let active = true;

    async function refresh() {
      try {
        const {
          data: { session },
        } = await createClient().auth.getSession();
        if (!session) return;
        const feed = await listNotifications(session.access_token, 1);
        if (!active) return;
        setLiveUnreadCount(feed.unread_count);
        setUnresolvedSentBackCount(feed.unresolved_sent_back_count);
        if (showUrgentAlerts) {
          const alerts = await listAlerts(session.access_token);
          if (!active) return;
          setUrgentAlert(
            alerts.find(
              (alert) =>
                alert.acknowledged_at === null && alert.resolution_note === null,
            ) ?? null,
          );
        }
      } catch {
        // Keep the last confirmed badge and alert until a later poll succeeds.
      }
    }

    void refresh();
    const interval = window.setInterval(() => void refresh(), alertPollIntervalMs);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [pollStatus, showUrgentAlerts]);

  return (
    <div className={`mx-auto flex min-h-screen flex-col bg-bg ${wide ? "max-w-[1180px]" : "max-w-[430px]"}`}>
      {urgentAlert && alertsHref && (
        <Link href={alertsHref} className="block" aria-label={t("alert.banner.open")}>
          <Banner
            tone="urgent"
            title={t("alert.banner.title")}
            detail={t("alert.banner.detail", {
              location: urgentAlert.location_text ?? t("alert.locationUnknown"),
            })}
          />
        </Link>
      )}
      <header className="flex items-center gap-2 px-5 pb-2 pt-4">
        {title ? (
          <h1 className="min-w-0 flex-1 text-xl font-bold text-ink">{title}</h1>
        ) : (
          <>
            <span className="text-2xl" aria-hidden="true">{avatar}</span>
            <div className="min-w-0 flex-1 text-center">
              <p className="m-0 text-sm text-inkMuted">{greeting}</p>
              <p className="m-0 text-xl font-bold text-ink">{name}</p>
            </div>
          </>
        )}
        {languageSwitch}
        <Link
          className="relative grid min-h-11 min-w-11 place-items-center rounded-control border border-border bg-surface"
          href={inboxHref}
          aria-label={inboxLabel}
        >
          {inboxIcon}
          {liveUnreadCount > 0 && (
            <span className="absolute -right-1 -top-1 min-w-5 rounded-chip bg-danger px-1 text-center text-xs font-bold text-ink-inverse">
              {liveUnreadCount}
            </span>
          )}
          {unresolvedSentBackCount > 0 && (
            <span
              className="absolute -left-1 -top-1 min-w-5 rounded-chip bg-warning px-1 text-center text-xs font-bold text-ink ring-2 ring-warningTint"
              aria-label={priorityBadgeLabel?.(unresolvedSentBackCount)}
            >
              {unresolvedSentBackCount}
            </span>
          )}
        </Link>
      </header>
      <main className="flex-1 px-5 py-1">{children}</main>
      <nav className="sticky bottom-0 flex border-t border-border bg-bg px-2 py-2">
        {navItems.map((item) => (
          <Link
            className={`flex min-h-11 flex-1 flex-col items-center justify-center gap-1 text-xs font-bold ${
              item.href === activeHref ? "text-primary" : "text-inkMuted"
            }`}
            href={item.href}
            key={item.href}
          >
            {item.icon}
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
