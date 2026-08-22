import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewDecisionPage } from "../components/reports/ReviewDecisionPage";
import { defaultLocale, locales } from "../lib/locales";
import { mediaPhase } from "../lib/media";
import {
  getReport,
  getTimeline,
  reviewReport,
  type ReportDetail,
} from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";

vi.mock("../lib/reports", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/reports")>();
  return {
    ...original,
    getReport: vi.fn(),
    getTimeline: vi.fn(),
    reviewReport: vi.fn(),
  };
});
vi.mock("../lib/supabase/browser", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "test-token" } },
      }),
      getUser: async () => ({ data: { user: null } }),
    },
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/review/report-id",
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

const report: ReportDetail = {
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
  available_transitions: [
    {
      event: "reject",
      target: reportStatus.rejected,
      requires_reason: true,
      review_decision: "reject",
    },
    {
      event: "request_info",
      target: reportStatus.info_requested,
      requires_reason: true,
      review_decision: "request_info",
    },
    {
      event: "escalate",
      target: reportStatus.escalated,
      requires_reason: true,
      review_decision: "escalate",
    },
    {
      event: "approve_action",
      target: reportStatus.action_assigned,
      requires_reason: false,
      review_decision: "approve",
    },
  ],
};

const timeline = [
  {
    id: "audit-id",
    event: "queue_for_review",
    actor_type: "system" as const,
    actor_role: null,
    source: reportStatus.ai_drafted,
    target: reportStatus.under_review,
    reason: null,
    created_at: "2026-08-22T01:02:00Z",
  },
];

function renderReview(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <ReviewDecisionPage id="report-id" requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("ReviewDecisionPage", () => {
  beforeEach(() => {
    vi.mocked(getReport).mockReset();
    vi.mocked(getTimeline).mockReset();
    vi.mocked(reviewReport).mockReset();
    vi.mocked(getReport).mockResolvedValue(report);
    vi.mocked(getTimeline).mockResolvedValue(timeline);
    vi.mocked(reviewReport).mockResolvedValue({
      review_id: "review-id",
      report_id: "report-id",
      status: reportStatus.info_requested,
      assignment_id: null,
      corrective_action_id: null,
    });
  });
  afterEach(cleanup);

  it("renders full report context and only server-returned review paths", async () => {
    renderReview();

    expect(await screen.findByText(report.human_ref)).toBeTruthy();
    expect(screen.getByText(report.description_original)).toBeTruthy();
    expect(screen.getByText(report.description_en!)).toBeTruthy();
    expect(screen.getByRole("img", { name: "Level 6 edge" })).toBeTruthy();
    expect(screen.getByText(en["timeline.event.queue_for_review"])).toBeTruthy();
    expect(screen.getByRole("button", { name: en["action.reject"] })).toBeTruthy();
    expect(screen.getByRole("button", { name: en["action.approve_action"] })).toBeTruthy();
    expect(screen.getByRole("button", { name: en["action.request_info"] })).toBeTruthy();
    expect(screen.getByRole("button", { name: en["action.escalate"] })).toBeTruthy();
  });

  it("does not invent a decision the server omitted", async () => {
    vi.mocked(getReport).mockResolvedValue({
      ...report,
      available_transitions: [report.available_transitions[0]],
    });
    renderReview();

    expect(
      await screen.findByRole("button", { name: en["action.reject"] }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: en["action.approve_action"] }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: en["action.request_info"] }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: en["action.escalate"] }),
    ).toBeNull();
  });

  it("requires the state-machine reason before submitting rejection", async () => {
    const user = userEvent.setup();
    renderReview();
    await user.click(
      await screen.findByRole("button", { name: en["action.reject"] }),
    );

    const submit = screen.getByRole<HTMLButtonElement>("button", {
      name: en["action.reject"],
    });
    expect(submit.disabled).toBe(true);
    await user.type(
      screen.getByLabelText(en["review.detail.reason"]),
      "This is not a site hazard.",
    );
    expect(submit.disabled).toBe(false);
    await user.click(submit);

    await waitFor(() =>
      expect(reviewReport).toHaveBeenCalledWith(
        "report-id",
        expect.objectContaining({
          decision: "reject",
          target: reportStatus.rejected,
          reason: "This is not a site hazard.",
        }),
        "test-token",
      ),
    );
  });

  it("collects action, correction reason, assignee and due date for approval", async () => {
    const user = userEvent.setup();
    renderReview();
    await user.click(
      await screen.findByRole("button", { name: en["action.approve_action"] }),
    );
    await user.click(screen.getByText(en["review.detail.corrections"]));
    await user.type(
      screen.getByLabelText(en["review.detail.correctedAction"]),
      "Install secured guardrails.",
    );
    await user.type(
      screen.getByLabelText(en["review.detail.correctionReason"]),
      "The action was missing.",
    );
    await user.type(
      screen.getByLabelText(en["review.detail.assigneeId"]),
      "00000000-0000-0000-0000-000000000004",
    );
    fireEvent.change(screen.getByLabelText(en["review.detail.dueAt"]), {
      target: { value: "2026-08-25T12:00" },
    });

    const submit = screen.getByRole<HTMLButtonElement>("button", {
      name: en["action.approve_action"],
    });
    expect(submit.disabled).toBe(false);
    await user.click(submit);

    await waitFor(() =>
      expect(reviewReport).toHaveBeenCalledWith(
        "report-id",
        expect.objectContaining({
          decision: "approve",
          target: reportStatus.action_assigned,
          corrected_action: "Install secured guardrails.",
          correction_reason: "The action was missing.",
          assignee_id: "00000000-0000-0000-0000-000000000004",
          due_at: expect.stringContaining("2026-08-25T"),
        }),
        "test-token",
      ),
    );
  });

  it("renders the review context and decisions in Simplified Chinese", async () => {
    renderReview(locales[1]);

    expect(await screen.findByText(zh["review.detail.report"])).toBeTruthy();
    expect(screen.getByText(zh["timeline.event.queue_for_review"])).toBeTruthy();
    expect(screen.getByRole("button", { name: zh["action.reject"] })).toBeTruthy();
  });
});
