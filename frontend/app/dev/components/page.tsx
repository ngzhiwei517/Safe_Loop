"use client";

import { useState } from "react";

import { AppShell } from "../../../components/ui/AppShell";
import { Banner } from "../../../components/ui/Banner";
import { Card } from "../../../components/ui/Card";
import { PrimaryButton, SecondaryButton, DestructiveButton } from "../../../components/ui/Buttons";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Field } from "../../../components/ui/Field";
import { IconTile } from "../../../components/ui/IconTile";
import { LanguageSwitch } from "../../../components/ui/LanguageSwitch";
import { PhotoStrip } from "../../../components/ui/PhotoStrip";
import { Sheet } from "../../../components/ui/Sheet";
import { StatusChip } from "../../../components/ui/StatusChip";
import { Timeline } from "../../../components/ui/Timeline";
import { reportStatuses } from "../../../lib/stateMachine";
import { notFound } from "next/navigation";

export default function ComponentsPage() {
  if (process.env.NODE_ENV === "production") notFound();
  const [locale, setLocale] = useState("en");
  return <main className="min-h-screen bg-bg p-5 text-ink"><div className="mx-auto max-w-5xl space-y-8"><header><p className="text-sm font-bold uppercase tracking-wide text-inkMuted">Development gallery</p><h1 className="mt-2 text-3xl font-bold">SafeLoop UI foundation</h1></header><LanguageSwitch current={locale} options={[{ value: "en", label: "English" }, { value: "zh-CN", label: "简体中文" }]} onChange={setLocale} /><section className="grid gap-3 sm:grid-cols-2"><Card><h2 className="text-xl font-bold">Card</h2><p className="mt-2 text-base">A quiet surface for information that needs a clear edge.</p></Card><div className="space-y-3"><PrimaryButton label="Primary action" /><SecondaryButton label="Secondary action" /><DestructiveButton label="Destructive action" /></div></section><section className="space-y-3"><h2 className="text-xl font-bold">Status chips</h2><div className="flex flex-wrap gap-2">{reportStatuses.map((status) => <StatusChip key={status} status={status} label={status} />)}</div></section><section className="grid gap-3 sm:grid-cols-2"><IconTile>!</IconTile><Field label="Location" placeholder="Enter a location" error="Example error" /><PhotoStrip photos={[]} addLabel="Add photo" /><Timeline events={[{ title: "Submitted", detail: "Today · 09:12", state: "now" }, { title: "Waiting for review", detail: "Next step", state: "todo" }]} /></section><section className="space-y-3"><Banner tone="info" title="Information banner" detail="A calm explanation for context." /><Banner tone="warning" title="Warning banner" detail="A decision needs attention." /><Banner tone="urgent" title="Urgent banner" detail="A person needs action now." /></section><EmptyState icon="○" title="Nothing here yet" detail="The empty state gives the next action a clear place." action={<PrimaryButton label="Start" />} /><Sheet title="Sheet" closeLabel="Close"><p className="text-base">A dismissible reading surface for decisions.</p></Sheet><AppShell greeting="Good morning" name="Demo worker" inboxLabel="Inbox" unreadCount={2} activeHref="/" navItems={[{ href: "/", label: "Home", icon: "⌂" }, { href: "/reports", label: "My Reports", icon: "▤" }, { href: "/learn", label: "Learn", icon: "▥" }, { href: "/profile", label: "Profile", icon: "○" }]}><Card><p className="text-base">Shell preview · {locale}</p></Card></AppShell></div></main>;
}
