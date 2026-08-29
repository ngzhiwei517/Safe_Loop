import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearnPage } from "../components/learning/LearnPage";
import { listLearningBriefings } from "../lib/briefings";
import en from "../messages/en.json";
import { learningBriefingsFixture } from "./fixtures/learning";

vi.mock("../lib/briefings", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/briefings")>();
  return { ...original, listLearningBriefings: vi.fn() };
});
vi.mock("../lib/notifications", () => ({
  listNotifications: vi.fn(async () => ({
    unread_count: 0,
    priority_unread_count: 0,
    unresolved_sent_back_count: 0,
    items: [],
  })),
}));
vi.mock("../lib/alerts", () => ({ listAlerts: vi.fn(async () => []) }));
vi.mock("../lib/supabase/browser", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "test-token" } },
      }),
    },
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/learn",
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

describe("LearnPage", () => {
  beforeEach(() => {
    vi.mocked(listLearningBriefings).mockReset();
    vi.mocked(listLearningBriefings).mockResolvedValue(learningBriefingsFixture);
  });
  afterEach(cleanup);

  it("keeps the server-ranked target lesson first and shows quiz state", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={expand(en)}>
        <LearnPage requestedLocale="en" role="crew" />
      </NextIntlClientProvider>,
    );

    expect(await screen.findByText(en["learn.item.forYou"])).toBeTruthy();
    expect(screen.getByText(en["learn.item.answered"])).toBeTruthy();
    expect(screen.getByText(en["learn.item.notAnswered"])).toBeTruthy();
    const links = screen.getAllByRole<HTMLAnchorElement>("link", {
      name: en["learn.item.open"],
    });
    expect(links[0].getAttribute("href")).toBe("/en/b/target-token");
    expect(links[1].getAttribute("href")).toBe("/en/b/newest-token");
  });

  it("keeps the reviewer navigation when a reviewer opens shared learning", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={expand(en)}>
        <LearnPage requestedLocale="en" role="reviewer" />
      </NextIntlClientProvider>,
    );

    await screen.findByText(en["learn.item.forYou"]);
    expect(screen.getByRole("link", { name: en["review.nav.queue"] }).getAttribute("href")).toBe("/en/review");
    expect(screen.getByRole("link", { name: en["review.nav.documents"] }).getAttribute("href")).toBe("/en/documents");
    expect(screen.getByRole("link", { name: en["review.nav.briefings"] }).getAttribute("href")).toBe("/en/briefings");
    expect(screen.getByRole("link", { name: en["review.nav.dashboard"] }).getAttribute("href")).toBe("/en/dashboard");
    expect(screen.getByRole("link", { name: en["app.profile"] }).getAttribute("href"))
      .toBe("/en/profile");
    expect(screen.queryByRole("link", { name: en["app.myReports"] })).toBeNull();
  });

  it("shows the complete reporter navigation with the profile tab", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={expand(en)}>
        <LearnPage requestedLocale="en" role="reporter" />
      </NextIntlClientProvider>,
    );

    await screen.findByText(en["learn.item.forYou"]);
    expect(screen.getByRole("link", { name: en["app.home"] }).getAttribute("href"))
      .toBe("/en/report/new");
    expect(screen.getByRole("link", { name: en["app.myReports"] }).getAttribute("href"))
      .toBe("/en/reports");
    expect(screen.getByRole("link", { name: en["app.learn"] }).getAttribute("href"))
      .toBe("/en/learn");
    expect(screen.getByRole("link", { name: en["app.profile"] }).getAttribute("href"))
      .toBe("/en/profile");
  });
});
