import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BriefingsPage } from "../components/briefings/BriefingsPage";
import { listManagedBriefings } from "../lib/briefings";
import { defaultLocale, locales } from "../lib/locales";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";
import { briefingFixture } from "./fixtures/briefing";

vi.mock("../lib/briefings", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/briefings")>();
  return { ...original, listManagedBriefings: vi.fn() };
});
vi.mock("../lib/notifications", () => ({ listNotifications: vi.fn(async () => ({ unread_count: 0, priority_unread_count: 0, unresolved_sent_back_count: 0, items: [] })) }));
vi.mock("../lib/alerts", () => ({ listAlerts: vi.fn(async () => []) }));
vi.mock("../lib/supabase/browser", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "test-token" } } }) },
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/briefings",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

function expand(flat: Record<string, string>): AbstractIntlMessages {
  const result: AbstractIntlMessages = {};
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split(".");
    let cursor: AbstractIntlMessages = result;
    for (const part of parts.slice(0, -1)) {
      cursor = (cursor[part] ??= {}) as AbstractIntlMessages;
    }
    cursor[parts.at(-1)!] = value;
  }
  return result;
}

function renderBriefings(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <BriefingsPage requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("BriefingsPage", () => {
  beforeEach(() => {
    vi.mocked(listManagedBriefings).mockReset();
    vi.mocked(listManagedBriefings).mockResolvedValue([briefingFixture]);
  });
  afterEach(cleanup);

  it("lists the draft version and its target", async () => {
    renderBriefings();
    expect(await screen.findByText("SL-2026-00042 · version 1")).toBeTruthy();
    expect(screen.getByText("Formwork · Level 6")).toBeTruthy();
    expect(
      screen.getByRole<HTMLAnchorElement>("link", { name: en["briefings.item.open"] }).getAttribute("href"),
    ).toBe("/en/briefings/briefing-one");
  });

  it("renders the list chrome in Simplified Chinese", async () => {
    renderBriefings(locales[1]);
    expect(await screen.findByText(zh["briefings.title"])).toBeTruthy();
    expect(screen.getByRole("link", { name: zh["briefings.item.open"] })).toBeTruthy();
  });
});
