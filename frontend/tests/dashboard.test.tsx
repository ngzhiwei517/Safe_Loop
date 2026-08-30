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
  report_count: 20,
  voice_report_count: 8,
  voice_report_share: 0.4,
  transcript_accepted_unedited_rate: 0.625,
  median_voice_edit_distance: 1,
  transcription_attempt_count: 12,
  transcription_failure_count: 2,
  transcription_failure_rate: 1 / 6,
  voice_by_detected_locale: [
    {
      detected_locale: "zh-CN",
      voice_report_count: 5,
      voice_unedited_count: 3,
      voice_edited_count: 2,
      transcript_accepted_unedited_rate: 0.6,
      median_edit_distance: 1,
      transcription_attempt_count: 7,
      transcription_failure_count: 1,
      transcription_failure_rate: 1 / 7,
    },
    {
      detected_locale: "en-SG",
      voice_report_count: 3,
      voice_unedited_count: 2,
      voice_edited_count: 1,
      transcript_accepted_unedited_rate: 2 / 3,
      median_edit_distance: 1,
      transcription_attempt_count: 5,
      transcription_failure_count: 1,
      transcription_failure_rate: 0.2,
    },
  ],
  open_by_status: { under_review: 3, action_assigned: 2 },
  overdue_count: 1,
  rework_rate: 0.5,
  median_verification_cycles_to_close: 2,
  median_submitted_to_under_review_seconds: 180,
  median_submitted_to_action_assigned_seconds: 14_400,
  median_action_assigned_to_verified_closed_seconds: 27_000,
  reviewer_correction_rate: 0.25,
  published_briefing_count: 2,
  crew_reach: 6,
  anonymous_quiz_response_count: 2,
  first_attempt_count: 8,
  first_attempt_pass_rate: 0.75,
  question_performance: [
    {
      question_id: "10000000-0000-0000-0000-000000000001",
      briefing_id: "20000000-0000-0000-0000-000000000001",
      position: 1,
      question: { en: "What should the crew check first?", "zh-CN": "工友首先要检查什么？" },
      first_attempt_count: 4,
      first_attempt_correct_count: 3,
      first_attempt_wrong_count: 1,
      first_attempt_pass_rate: 0.75,
    },
    {
      question_id: "10000000-0000-0000-0000-000000000002",
      briefing_id: "20000000-0000-0000-0000-000000000001",
      position: 2,
      question: { en: "When should work stop?", "zh-CN": "什么时候必须停工？" },
      first_attempt_count: 4,
      first_attempt_correct_count: 2,
      first_attempt_wrong_count: 2,
      first_attempt_pass_rate: 0.5,
    },
  ],
  questions_most_often_wrong: [
    {
      question_id: "10000000-0000-0000-0000-000000000002",
      briefing_id: "20000000-0000-0000-0000-000000000001",
      position: 2,
      question: { en: "When should work stop?", "zh-CN": "什么时候必须停工？" },
      first_attempt_count: 4,
      first_attempt_correct_count: 2,
      first_attempt_wrong_count: 2,
      first_attempt_pass_rate: 0.5,
    },
  ],
  repeat_hazard_window_days: 90,
  repeat_hazards: [
    {
      category: "work_at_height",
      location: "Block A",
      report_count: 3,
      recurrence_count: 2,
      first_closed_at: "2026-07-01T00:00:00Z",
      latest_closed_at: "2026-08-20T00:00:00Z",
      responsible_rework: [
        {
          profile_id: "30000000-0000-0000-0000-000000000001",
          display_name: "Fixture Responsible",
          action_count: 4,
          reworked_action_count: 2,
          rework_rate: 0.5,
        },
      ],
    },
  ],
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
    expect(screen.getByText(en["dashboard.voiceQuality"])).toBeTruthy();
    expect(screen.getByText("zh-CN")).toBeTruthy();
    expect(screen.getByText("en-SG")).toBeTruthy();
    expect(
      screen.getAllByText(formatPercent(0.5, defaultLocale)).length,
    ).toBeGreaterThan(0);
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
    expect(screen.getByText(en["dashboard.learningQuestion"])).toBeTruthy();
    expect(screen.getAllByText(formatPercent(0.75, defaultLocale))).toHaveLength(2);
    expect(screen.getByText("What should the crew check first?")).toBeTruthy();
    expect(screen.getByText(en["dashboard.mostOftenWrong"])).toBeTruthy();
    expect(screen.getByText("work_at_height")).toBeTruthy();
    expect(screen.getByText("Fixture Responsible")).toBeTruthy();
    expect(getMetricsSummary).toHaveBeenCalledWith("test-token");
  });

  it("renders the same metric contract in Simplified Chinese", async () => {
    renderDashboard(locales[1]);

    expect(await screen.findByText(zh["dashboard.title"])).toBeTruthy();
    expect(screen.getByText(zh["dashboard.openByStatus"])).toBeTruthy();
    expect(
      screen.getAllByText(formatPercent(0.5, locales[1])).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(zh["dashboard.learningQuestion"])).toBeTruthy();
    expect(screen.getByText("工友首先要检查什么？")).toBeTruthy();
    expect(screen.getByText(zh["dashboard.mostOftenWrong"])).toBeTruthy();
  });
});
