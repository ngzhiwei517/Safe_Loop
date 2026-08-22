"use client";

import { useLocale, useTranslations } from "next-intl";

import { defaultLocale, formatDateTime, isLocale, locales } from "../../lib/locales";
import { reportStatuses } from "../../lib/stateMachine";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { DestructiveButton, PrimaryButton, SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Field } from "../ui/Field";
import { IconTile } from "../ui/IconTile";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { PhotoStrip } from "../ui/PhotoStrip";
import { Sheet } from "../ui/Sheet";
import { StatusChip } from "../ui/StatusChip";
import { Timeline } from "../ui/Timeline";

export function ComponentsGallery() {
  const t = useTranslations();
  const requestedLocale = useLocale();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const options = [
    { value: locales[0], label: t("app.languageEnglish") },
    { value: locales[1], label: t("app.languageChinese") },
  ];
  const languageSwitch = <LanguageSwitch current={locale} options={options} label={t("app.language")} />;
  const navItems = [
    { href: `/${locale}`, label: t("app.home"), icon: "⌂" },
    { href: `/${locale}/reports`, label: t("app.myReports"), icon: "▤" },
    { href: `/${locale}/learn`, label: t("app.learn"), icon: "▥" },
    { href: `/${locale}/profile`, label: t("app.profile"), icon: "○" },
  ];

  return <main className="min-h-screen bg-bg p-5 text-ink"><div className="mx-auto max-w-5xl space-y-8"><header><p className="text-sm font-bold uppercase tracking-wide text-inkMuted">{t("dev.gallery")}</p><h1 className="mt-2 text-3xl font-bold">{t("dev.title")}</h1></header>{languageSwitch}<section className="grid gap-3 sm:grid-cols-2"><Card><h2 className="text-xl font-bold">{t("dev.card")}</h2><p className="mt-2 text-base">{t("dev.cardDetail")}</p></Card><div className="space-y-3"><PrimaryButton label={t("dev.primary")} /><SecondaryButton label={t("dev.secondary")} /><DestructiveButton label={t("dev.destructive")} /></div></section><section className="space-y-3"><h2 className="text-xl font-bold">{t("dev.statuses")}</h2><div className="flex flex-wrap gap-2">{reportStatuses.map((status) => <StatusChip key={status} status={status} label={t(`status.${status}`)} />)}</div></section><section className="grid gap-3 sm:grid-cols-2"><IconTile>{"!"}</IconTile><Field label={t("dev.location")} placeholder={t("dev.locationPlaceholder")} error={t("dev.exampleError")} /><PhotoStrip photos={[]} addLabel={t("dev.addPhoto")} addIcon={"+"} /><Timeline events={[{ title: t("status.submitted"), detail: formatDateTime(new Date(2026, 7, 22, 9, 12), locale), state: "now" }, { title: t("dev.waiting"), detail: t("dev.nextStep"), state: "todo" }]} /></section><section className="space-y-3"><Banner tone="info" title={t("dev.infoTitle")} detail={t("dev.infoDetail")} /><Banner tone="warning" title={t("dev.warningTitle")} detail={t("dev.warningDetail")} /><Banner tone="urgent" title={t("dev.urgentTitle")} detail={t("dev.urgentDetail")} /></section><EmptyState icon={"○"} title={t("dev.emptyTitle")} detail={t("dev.emptyDetail")} action={<PrimaryButton label={t("dev.start")} />} /><Sheet title={t("dev.sheet")} closeLabel={t("dev.close")} closeIcon={"×"}><p className="text-base">{t("dev.sheetDetail")}</p></Sheet><AppShell greeting={t("app.goodMorning")} name={t("dev.worker")} avatar={"👷"} inboxHref={`/${locale}/inbox`} inboxLabel={t("app.inbox")} inboxIcon={"◌"} unreadCount={2} activeHref={`/${locale}`} navItems={navItems} languageSwitch={languageSwitch}><Card><p className="text-base">{t("dev.shellPreview")}</p></Card></AppShell></div></main>;
}
