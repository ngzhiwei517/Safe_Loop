import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VerificationPage } from "../components/reports/VerificationPage";
import { defaultLocale, locales } from "../lib/locales";
import { mediaPhase } from "../lib/media";
import {
  getReport,
  verifyReport,
  type ReportDetail,
} from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";

vi.mock("../lib/reports", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/reports")>();
  return { ...original, getReport: vi.fn(), verifyReport: vi.fn() };
});
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
  usePathname: () => "/en/verify/report-id",
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
  human_ref: "SL-2026-00042",
  status: reportStatus.action_submitted,
  urgency: "high",
  lang_original: defaultLocale,
  description_original: "Loose edge guardrail",
  description_en: null,
  location_text: "Level 6 east edge",
  activity: "Formwork",
  level_or_zone: "Level 6",
  grid_ref: null,
  submitted_at: "2026-08-20T00:02:00Z",
  closed_at: null,
  created_at: "2026-08-20T00:00:00Z",
  media: [
    {
      id: "evidence-id",
      storage_path: "responsible/report/evidence.jpg",
      mime_type: "image/jpeg",
      phase: mediaPhase.evidence,
      caption: null,
      corrective_action_id: "action-id",
      created_at: "2026-08-23T02:00:00Z",
      signed_url: "https://project.example/evidence.jpg?token=signed",
      signed_url_expires_at: "2099-08-23T02:10:00Z",
    },
  ],
  latest_draft: null,
  current_action: {
    id: "action-id",
    assignment_id: "assignment-id",
    assignee_id: "responsible-id",
    assignee_name: "Ah Hock",
    assignment_active: true,
    action_text: "Secure every guardrail anchor before work resumes.",
    status: "submitted",
    rework_count: 1,
    due_at: "2099-08-30T09:00:00Z",
    completed_note: "Replaced the lower anchor and pull-tested both anchors.",
    submitted_at: "2026-08-23T02:00:00Z",
  },
  verifications: [
    {
      id: "verification-one",
      corrective_action_id: "action-id",
      reviewer_id: "reviewer-id",
      reviewer_name: "SO Lim",
      passed: false,
      checklist: { hazard_removed: false, same_location: true },
      notes: "The lower anchor was pull-tested.",
      reason: "The lower anchor still moved when pulled.",
      new_due_at: "2099-08-30T09:00:00Z",
      created_at: "2026-08-22T01:00:00Z",
    },
  ],
  closure_receipt: null,
  available_transitions: [
    {
      event: "verification_failed",
      target: reportStatus.action_assigned,
      requires_reason: true,
    },
    {
      event: "verify_and_close",
      target: reportStatus.verified_closed,
      requires_reason: false,
    },
  ],
};

function renderVerification(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <VerificationPage id={report.id} requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("VerificationPage", () => {
  beforeEach(() => {
    vi.mocked(getReport).mockReset();
    vi.mocked(verifyReport).mockReset();
    vi.mocked(getReport).mockResolvedValue(report);
    vi.mocked(verifyReport).mockResolvedValue({
      verification_id: "verification-two",
      report_id: report.id,
      status: reportStatus.action_assigned,
      closed_at: null,
      corrective_action_id: "action-id",
      action_status: "assigned",
      rework_count: 2,
      assignment_id: "assignment-id",
      due_at: "2099-09-01T09:00:00Z",
    });
  });
  afterEach(cleanup);

  it("puts submitted proof and the complete prior deficiency before the decision", async () => {
    renderVerification();

    const proof = await screen.findByText(report.current_action!.completed_note!);
    const priorReason = screen.getAllByText(report.verifications[0].reason!)[0];
    const decision = screen.getByText(en["verification.checklist.title"]);
    expect(
      proof.compareDocumentPosition(decision) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      priorReason.compareDocumentPosition(decision) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole("img", { name: en["verification.evidence.photoAlt"] }),
    ).toBeTruthy();
  });

  it("rejects a generic send-back reason and submits the specific deficiency", async () => {
    renderVerification();
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: en["action.verification_failed"] }),
    );
    await user.type(
      screen.getByRole("textbox", { name: en["verification.notes.label"] }),
      "The lower anchor was pull-tested.",
    );
    const reason = screen.getByRole("textbox", {
      name: en["verification.failure.reasonLabel"],
    });
    await user.type(reason, "not done");
    fireEvent.change(
      screen.getByLabelText(en["verification.failure.newDueLabel"]),
      { target: { value: "2099-09-01T17:00" } },
    );
    expect(screen.getByText(en["error.verification_reason_too_vague"])).toBeTruthy();
    expect(
      screen.getByRole<HTMLButtonElement>("button", {
        name: en["action.verification_failed"],
      }).disabled,
    ).toBe(true);

    await user.clear(reason);
    await user.type(reason, "The lower anchor still moves when pulled.");
    await user.click(
      screen.getByRole("button", { name: en["action.verification_failed"] }),
    );

    await waitFor(() =>
      expect(verifyReport).toHaveBeenCalledWith(
        report.id,
        {
          passed: false,
          checklist: {
            hazard_removed: false,
            same_location: false,
            no_new_hazard: false,
          },
          notes: "The lower anchor was pull-tested.",
          reason: "The lower anchor still moves when pulled.",
          new_due_at: new Date("2099-09-01T17:00").toISOString(),
        },
        "test-token",
      ),
    );
  });

  it("closes only after the server offers closure and every check is confirmed", async () => {
    renderVerification();
    const user = userEvent.setup();

    await screen.findByText(en["verification.checklist.title"]);
    for (const item of [
      en["verification.checklist.hazardRemoved"],
      en["verification.checklist.sameLocation"],
      en["verification.checklist.noNewHazard"],
    ]) {
      await user.click(screen.getByRole("checkbox", { name: item }));
    }
    await user.type(
      screen.getByRole("textbox", { name: en["verification.notes.label"] }),
      "All anchors passed the final pull test.",
    );
    await user.click(
      screen.getByRole("button", { name: en["action.verify_and_close"] }),
    );
    await user.click(
      screen.getByRole("button", { name: en["action.verify_and_close"] }),
    );

    await waitFor(() =>
      expect(verifyReport).toHaveBeenCalledWith(
        report.id,
        {
          passed: true,
          checklist: {
            hazard_removed: true,
            same_location: true,
            no_new_hazard: true,
          },
          notes: "All anchors passed the final pull test.",
          reason: undefined,
          new_due_at: undefined,
        },
        "test-token",
      ),
    );
  });

  it("renders only the decision paths returned by the server in Chinese", async () => {
    vi.mocked(getReport).mockResolvedValue({
      ...report,
      available_transitions: [report.available_transitions[0]],
    });
    renderVerification(locales[1]);

    expect(
      await screen.findByRole("button", { name: zh["action.verification_failed"] }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: zh["action.verify_and_close"] }),
    ).toBeNull();
    expect(screen.getByText(zh["verification.history.title"])).toBeTruthy();
  });
});
