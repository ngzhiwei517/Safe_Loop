"use client";

import {
  BellAlertIcon,
  BellIcon,
  MapPinIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  acknowledgeAlert,
  listAlerts,
  resolveAlert,
  type AlertItem,
} from "../../lib/alerts";
import { defaultLocale, formatDateTime, isLocale, locales } from "../../lib/locales";
import { siteEmergencyLine } from "../../lib/site";
import { createClient } from "../../lib/supabase/browser";
import {
  type OperationsRole,
  useOperationsNavigation,
} from "../navigation/useOperationsNavigation";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { PrimaryButton, SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Field } from "../ui/Field";
import { LanguageSwitch } from "../ui/LanguageSwitch";

function alertStateKey(alert: AlertItem): string {
  if (alert.resolution_note) return "alert.state.resolved";
  if (alert.acknowledged_at) return "alert.state.acknowledged";
  if (alert.escalated_at) return "alert.state.escalated";
  return "alert.state.sent";
}

export function AlertsPage({
  requestedLocale,
  role = "reviewer",
}: {
  requestedLocale: string;
  role?: OperationsRole;
}) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const navItems = useOperationsNavigation(locale, role);
  const [items, setItems] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [resolutionId, setResolutionId] = useState<string | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      setItems(await listAlerts(session.access_token));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function acknowledge(alertId: string) {
    setSavingId(alertId);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      const updated = await acknowledgeAlert(alertId, session.access_token);
      setItems((current) => current.map((item) => item.id === alertId ? updated : item));
    } catch {
      setLoadFailed(true);
    } finally {
      setSavingId(null);
    }
  }

  async function resolve(alertId: string) {
    if (!resolutionNote.trim()) return;
    setSavingId(alertId);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("session_required");
      const updated = await resolveAlert(alertId, resolutionNote.trim(), session.access_token);
      setItems((current) => current.map((item) => item.id === alertId ? updated : item));
      setResolutionId(null);
      setResolutionNote("");
    } catch {
      setLoadFailed(true);
    } finally {
      setSavingId(null);
    }
  }

  return (
    <AppShell
      title={t("alert.list.title")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={0}
      pollStatus
      showUrgentAlerts
      alertsHref={`/${locale}/alerts`}
      navItems={navItems}
      activeHref={`/${locale}/alerts`}
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
        <Banner
          tone="urgent"
          title={t("alert.list.emergencyTitle")}
          detail={t("alert.reporter.emergency", { number: siteEmergencyLine })}
        />
        {loadFailed && (
          <Banner
            tone="warning"
            title={t("alert.list.loadFailedTitle")}
            detail={t("alert.list.loadFailedDetail")}
          />
        )}
        {loading ? (
          <p className="py-8 text-center text-base text-inkMuted" role="status">
            {t("alert.list.loading")}
          </p>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<BellAlertIcon className="h-8 w-8" />}
            title={t("alert.list.emptyTitle")}
            detail={t("alert.list.emptyDetail")}
          />
        ) : (
          items.map((alert) => (
            <Card className={`space-y-4 ${alert.acknowledged_at === null && alert.resolution_note === null ? "border-l-4 border-l-danger" : ""}`} key={alert.id}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-bold text-danger">{t(alertStateKey(alert))}</p>
                  <h2 className="text-xl font-bold">{alert.human_ref}</h2>
                </div>
                <BellAlertIcon className="h-8 w-8 text-danger" />
              </div>
              <p className="text-base">{alert.description_original}</p>
              <p className="flex items-center gap-2 text-sm text-inkMuted">
                <MapPinIcon className="h-5 w-5" />
                <span>{alert.location_text ?? t("alert.locationUnknown")}</span>
              </p>
              <p className="text-sm text-inkMuted">
                {t("alert.list.raisedAt", { time: formatDateTime(alert.raised_at, locale) })}
              </p>
              {alert.acknowledged_at && alert.acknowledged_by_name && (
                <p className="text-sm font-bold text-successStrong">
                  {t("alert.list.acknowledgedBy", {
                    name: alert.acknowledged_by_name,
                    time: formatDateTime(alert.acknowledged_at, locale),
                  })}
                </p>
              )}
              {alert.resolution_note && (
                <p className="rounded-control bg-successSurface p-3 text-sm">
                  {t("alert.list.resolution", { note: alert.resolution_note })}
                </p>
              )}
              {alert.acknowledged_at === null && alert.resolution_note === null && (
                <PrimaryButton
                  label={savingId === alert.id ? t("alert.list.saving") : t("alert.list.acknowledge")}
                  disabled={savingId !== null}
                  onClick={() => void acknowledge(alert.id)}
                />
              )}
              {alert.resolution_note === null && (
                resolutionId === alert.id ? (
                  <div className="space-y-3">
                    <Field
                      rows={3}
                      label={t("alert.list.resolutionNote")}
                      value={resolutionNote}
                      onChange={(event) => setResolutionNote(event.target.value)}
                    />
                    <PrimaryButton
                      label={savingId === alert.id ? t("alert.list.saving") : t("alert.list.resolve")}
                      disabled={!resolutionNote.trim() || savingId !== null}
                      onClick={() => void resolve(alert.id)}
                    />
                  </div>
                ) : (
                  <SecondaryButton
                    label={t("alert.list.addResolution")}
                    onClick={() => {
                      setResolutionId(alert.id);
                      setResolutionNote("");
                    }}
                  />
                )
              )}
            </Card>
          ))
        )}
      </section>
    </AppShell>
  );
}
