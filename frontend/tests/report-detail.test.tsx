import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportDetail } from "../components/reports/ReportDetail";
import { defaultLocale, locales } from "../lib/locales";
import { mediaPhase } from "../lib/media";
import {
  getReport,
  getTimeline,
  transitionReport,
  type ReportDetail as ReportDetailData,
} from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";

vi.mock("../lib/reports", () => ({
  getReport: vi.fn(),
  getTimeline: vi.fn(),
  transitionReport: vi.fn(),
}));
vi.mock("../lib/supabase/browser", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "test-token" } },
      }),
    },
  }),
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

function reportWith(
  availableTransitions: ReportDetailData["available_transitions"],
): ReportDetailData {
  return {
    id: "report-id",
    human_ref: "SL-2026-00001",
    status: reportStatus.under_review,
    urgency: "high",
    lang_original: locales[1],
    description_original: "六楼边缘没有护栏",
    description_en: "There is no guardrail at the Level 6 edge.",
    location_text: "Tower A",
    activity: "Material delivery",
    level_or_zone: "Level 6",
    grid_ref: "A4",
    created_at: "2026-08-22T01:00:00Z",
    media: [
      {
        id: "media-id",
        storage_path: "private/photo.jpg",
        mime_type: "image/jpeg",
        phase: mediaPhase.original,
        caption: "Level 6 edge",
        signed_url: "https://project.example/photo.jpg?token=signed",
        signed_url_expires_at: "2026-08-22T01:10:00Z",
      },
    ],
    available_transitions: availableTransitions,
  };
}

const timeline = [
  {
    id: "audit-id",
    event: "submit",
    actor_type: "human" as const,
    actor_role: "reporter" as const,
    source: reportStatus.draft,
    target: reportStatus.submitted,
    reason: null,
    created_at: "2026-08-22T01:02:00Z",
  },
];

function renderDetail(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <ReportDetail id="report-id" requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("ReportDetail", () => {
  beforeEach(() => {
    vi.mocked(getReport).mockReset();
    vi.mocked(getTimeline).mockReset();
    vi.mocked(transitionReport).mockReset();
    vi.mocked(getTimeline).mockResolvedValue(timeline);
    vi.mocked(transitionReport).mockResolvedValue({
      id: "report-id",
      status: reportStatus.rejected,
    });
  });
  afterEach(cleanup);

  it("renders only server-returned reviewer actions and enforces a reason", async () => {
    vi.mocked(getReport).mockResolvedValue(
      reportWith([
        { event: "reject", target: reportStatus.rejected, requires_reason: true },
        {
          event: "approve_action",
          target: reportStatus.action_assigned,
          requires_reason: false,
        },
      ]),
    );
    renderDetail();

    expect(await screen.findByText("There is no guardrail at the Level 6 edge.")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Level 6 edge" })).toBeTruthy();
    expect(screen.getByRole("button", { name: en["action.reject"] })).toBeTruthy();
    expect(screen.getByRole("button", { name: en["action.approve_action"] })).toBeTruthy();
    expect(screen.queryByRole("button", { name: en["action.request_info"] })).toBeNull();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: en["action.reject"] }));
    const reason = screen.getByLabelText(en["report.detail.reason"]);
    const submit = screen.getByRole<HTMLButtonElement>("button", { name: en["action.reject"] });
    expect(submit.disabled).toBe(true);
    await user.type(reason, "The observation is not a site hazard.");
    expect(submit.disabled).toBe(false);
    await user.click(submit);

    await waitFor(() =>
      expect(transitionReport).toHaveBeenCalledWith(
        "report-id",
        reportStatus.rejected,
        "test-token",
        "The observation is not a site hazard.",
      ),
    );
  });

  it("shows waiting copy when the server returns no reporter actions", async () => {
    vi.mocked(getReport).mockResolvedValue(reportWith([]));
    renderDetail();

    expect(await screen.findByText(en["report.detail.waiting.under_review"])).toBeTruthy();
    expect(screen.queryByText(en["report.detail.actions"])).toBeNull();
    expect(screen.queryByRole("button", { name: en["action.reject"] })).toBeNull();
  });

  it("renders timeline verbs and actors in Simplified Chinese", async () => {
    vi.mocked(getReport).mockResolvedValue(reportWith([]));
    renderDetail(locales[1]);

    expect(await screen.findByText(zh["timeline.event.submit"])).toBeTruthy();
    expect(screen.getByText(new RegExp(zh["timeline.actor.reporter"]))).toBeTruthy();
    expect(screen.getByText(zh["report.detail.originalText"])).toBeTruthy();
  });
});
