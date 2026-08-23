import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "../components/metrics/DashboardPage";
import {
  defaultLocale,
  formatDurationSeconds,
  formatPercent,
  locales,
} from "../lib/locales";
import { getMetricsSummary, type MetricsSummary } from "../lib/metrics";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";

vi.mock("../lib/metrics", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/metrics")>();
  return { ...original, getMetricsSummary: vi.fn() };
});
vi.mock("../lib/notifications", () => ({
  listNotifications: vi.fn(async () => ({
    items: [],
    unread_count: 0,
    priority_unread_count: 0,
    unresolved_sent_back_count: 0,
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
  usePathname: () => "/en/dashboard",
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

const metrics: MetricsSummary = {
  open_by_status: { under_review: 3, action_assigned: 2 },
  overdue_count: 1,
  rework_rate: 0.5,
  median_verification_cycles_to_close: 2,
  median_submitted_to_under_review_seconds: 180,
  median_submitted_to_action_assigned_seconds: 14_400,
  median_action_assigned_to_verified_closed_seconds: 27_000,
  reviewer_correction_rate: 0.25,
};

function renderDashboard(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <DashboardPage requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.mocked(getMetricsSummary).mockReset();
    vi.mocked(getMetricsSummary).mockResolvedValue(metrics);
  });
  afterEach(cleanup);

  it("renders the reconciled operational summary with explicit units", async () => {
    renderDashboard();

    expect(await screen.findByText(en["dashboard.openCases"])).toBeTruthy();
    expect(screen.getByText(formatPercent(0.5, defaultLocale))).toBeTruthy();
    expect(
      screen.getByText(formatDurationSeconds(180, defaultLocale)),
    ).toBeTruthy();
    expect(
      screen.getByText(formatDurationSeconds(14_400, defaultLocale)),
    ).toBeTruthy();
    expect(
      screen.getByText(formatDurationSeconds(27_000, defaultLocale)),
    ).toBeTruthy();
    expect(screen.getByText(formatPercent(0.25, defaultLocale))).toBeTruthy();
    expect(getMetricsSummary).toHaveBeenCalledWith("test-token");
  });

  it("renders the same metric contract in Simplified Chinese", async () => {
    renderDashboard(locales[1]);

    expect(await screen.findByText(zh["dashboard.title"])).toBeTruthy();
    expect(screen.getByText(zh["dashboard.openByStatus"])).toBeTruthy();
    expect(screen.getByText(formatPercent(0.5, locales[1]))).toBeTruthy();
  });
});
