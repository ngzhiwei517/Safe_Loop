import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportFlow } from "../components/reports/ReportFlow";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";
import { getAlert, raiseAlert } from "../lib/alerts";
import { defaultLocale, locales } from "../lib/locales";
import { createReportDraft, fileReport } from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";

const navigation = vi.hoisted(() => ({ push: vi.fn(), back: vi.fn() }));
const supabase = vi.hoisted(() => ({
  auth: {
    getSession: async () => ({
      data: {
        session: {
          access_token: "test-token",
          user: { id: "reporter-id" },
        },
      },
    }),
  },
  storage: {},
}));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
vi.mock("../lib/reports", () => ({
  createReportDraft: vi.fn(),
  fileReport: vi.fn(),
}));
vi.mock("../lib/alerts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/alerts")>();
  return { ...actual, getAlert: vi.fn(), raiseAlert: vi.fn() };
});
vi.mock("../lib/supabase/browser", () => ({ createClient: () => supabase }));

function expand(flat: Record<string, string>): AbstractIntlMessages {
  const result: AbstractIntlMessages = {};
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split(".");
    let cursor: AbstractIntlMessages = result;
    for (const part of parts.slice(0, -1)) cursor = (cursor[part] ??= {}) as AbstractIntlMessages;
    cursor[parts.at(-1)!] = value;
  }
  return result;
}

function renderFlow(locale = defaultLocale) {
  const flat = locale === defaultLocale ? en : zh;
  return render(<NextIntlClientProvider locale={locale} messages={expand(flat)}><ReportFlow /></NextIntlClientProvider>);
}

async function reachReview(description: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(en["report.new.whatHappened"]), description);
  await user.type(screen.getByLabelText(en["report.new.location"]), "Level 6");
  await user.click(screen.getByRole("button", { name: en["report.new.continue"] }));
  await user.click(screen.getByRole("button", { name: en["report.new.dangerNo"] }));
  await user.click(screen.getByRole("button", { name: en["report.new.continue"] }));
  await user.type(screen.getByLabelText(en["report.new.activity"]), "Material delivery");
  return user;
}

const sentAlert = {
  id: "alert-id",
  report_id: "draft-id",
  human_ref: "SL-2026-00001",
  description_original: "Loose edge protection",
  raised_by: "reporter-id",
  raised_at: "2026-08-22T08:00:00Z",
  location_text: "Level 6",
  acknowledged_by: null,
  acknowledged_by_name: null,
  acknowledged_at: null,
  escalated_at: null,
  resolution_note: null,
};

describe("ReportFlow", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    vi.mocked(createReportDraft).mockReset();
    vi.mocked(fileReport).mockReset();
    vi.mocked(getAlert).mockReset();
    vi.mocked(raiseAlert).mockReset();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:test-photo"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });
  afterEach(cleanup);

  it("creates a draft, submits it, and redirects", async () => {
    vi.mocked(fileReport).mockResolvedValue({ id: "report-id", human_ref: "SL-2026-00001", status: reportStatus.submitted });
    renderFlow();
    expect(screen.getByRole("link", { name: en["app.myReports"] }).getAttribute("href"))
      .toBe(`/${defaultLocale}/reports`);
    expect(screen.queryByRole("link", { name: en["app.profile"] })).toBeNull();
    const user = await reachReview("Loose edge protection");
    await user.click(screen.getByRole("button", { name: en["report.new.submit"] }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith(`/${defaultLocale}/report/report-id`));
    expect(fileReport).toHaveBeenCalledWith(
      expect.objectContaining({
        description_original: "Loose edge protection",
        input_mode: "typed",
      }),
      "test-token",
      undefined,
      undefined,
    );
  });

  it("passes the selected photo and authenticated storage client to submission", async () => {
    vi.mocked(fileReport).mockResolvedValue({ id: "report-id", human_ref: "SL-2026-00001", status: reportStatus.submitted });
    renderFlow();
    const file = new File(["photo"], "hazard.jpg", { type: "image/jpeg" });
    const inputElement = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(inputElement).not.toBeNull();
    await userEvent.upload(inputElement!, file);
    const user = await reachReview("Loose edge protection");
    await user.click(screen.getByRole("button", { name: en["report.new.submit"] }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith(`/${defaultLocale}/report/report-id`));
    expect(fileReport).toHaveBeenCalledWith(
      expect.any(Object),
      "test-token",
      expect.objectContaining({
        client: supabase,
        file,
        userId: "reporter-id",
        caption: "Loose edge protection",
      }),
      undefined,
    );
  });

  it("keeps typed input when submission fails", async () => {
    vi.mocked(fileReport).mockRejectedValue(new Error("offline"));
    renderFlow();
    const user = await reachReview("Keep this text");
    await user.click(screen.getByRole("button", { name: en["report.new.submit"] }));
    await screen.findByText(en["report.new.failureTitle"]);
    expect((screen.getByLabelText(en["report.new.whatHappened"]) as HTMLTextAreaElement).value).toBe("Keep this text");
  });

  it("raises an alert on the draft before submission and says sent, not seen", async () => {
    vi.mocked(createReportDraft).mockResolvedValue({ id: "draft-id" });
    vi.mocked(raiseAlert).mockResolvedValue(sentAlert);
    renderFlow();
    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText(en["report.new.whatHappened"]),
      "Loose edge protection",
    );
    await user.type(screen.getByLabelText(en["report.new.location"]), "Level 6");
    await user.click(screen.getByRole("button", { name: en["report.new.continue"] }));
    await user.click(screen.getByRole("button", { name: en["report.new.dangerYes"] }));

    expect(await screen.findByRole("heading", { name: en["alert.reporter.sent.title"] })).toBeTruthy();
    expect(screen.queryByText(/has seen/i)).toBeNull();
    expect(createReportDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        description_original: "Loose edge protection",
        location_text: "Level 6",
        input_mode: "typed",
      }),
      "test-token",
    );
    expect(raiseAlert).toHaveBeenCalledWith("draft-id", "Level 6", "test-token");
    expect(fileReport).not.toHaveBeenCalled();
  });

  it.each([[locales[0], en["report.new.captureTitle"]], [locales[1], zh["report.new.captureTitle"]]])("renders the capture page in %s", (locale, title) => {
    renderFlow(locale);
    expect(screen.getByRole("heading", { name: title })).toBeTruthy();
  });
});
