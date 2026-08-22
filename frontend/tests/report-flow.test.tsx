import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportFlow } from "../components/reports/ReportFlow";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";
import { defaultLocale, locales } from "../lib/locales";
import { fileReport } from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";

const navigation = vi.hoisted(() => ({ push: vi.fn(), back: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
vi.mock("../lib/reports", () => ({ fileReport: vi.fn() }));
vi.mock("../lib/supabase/browser", () => ({ createClient: () => ({ auth: { getSession: async () => ({ data: { session: { access_token: "test-token" } } }) } }) }));

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
  await user.click(screen.getByRole("button", { name: en["report.new.continue"] }));
  await user.click(screen.getByRole("button", { name: en["report.new.dangerNo"] }));
  await user.click(screen.getByRole("button", { name: en["report.new.continue"] }));
  await user.type(screen.getByLabelText(en["report.new.location"]), "Level 6");
  await user.type(screen.getByLabelText(en["report.new.activity"]), "Material delivery");
  return user;
}

describe("ReportFlow", () => {
  beforeEach(() => { navigation.push.mockReset(); vi.mocked(fileReport).mockReset(); });
  afterEach(cleanup);

  it("creates a draft, submits it, and redirects", async () => {
    vi.mocked(fileReport).mockResolvedValue({ id: "report-id", human_ref: "SL-2026-00001", status: reportStatus.submitted });
    renderFlow();
    const user = await reachReview("Loose edge protection");
    await user.click(screen.getByRole("button", { name: en["report.new.submit"] }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/en/report/report-id"));
    expect(fileReport).toHaveBeenCalledWith(expect.objectContaining({ description_original: "Loose edge protection", input_mode: "typed" }), "test-token");
  });

  it("keeps typed input when submission fails", async () => {
    vi.mocked(fileReport).mockRejectedValue(new Error("offline"));
    renderFlow();
    const user = await reachReview("Keep this text");
    await user.click(screen.getByRole("button", { name: en["report.new.submit"] }));
    await screen.findByText(en["report.new.failureTitle"]);
    expect((screen.getByLabelText(en["report.new.whatHappened"]) as HTMLTextAreaElement).value).toBe("Keep this text");
  });

  it.each([[locales[0], en["report.new.captureTitle"]], [locales[1], zh["report.new.captureTitle"]]])("renders the capture page in %s", (locale, title) => {
    renderFlow(locale);
    expect(screen.getByRole("heading", { name: title })).toBeTruthy();
  });
});
