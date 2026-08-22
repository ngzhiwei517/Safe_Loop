import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewQueue } from "../components/reports/ReviewQueue";
import { defaultLocale, locales } from "../lib/locales";
import { listReports, type ReportListItem } from "../lib/reports";
import { reportStatus, reportStatuses } from "../lib/stateMachine";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";

vi.mock("../lib/reports", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/reports")>();
  return { ...original, listReports: vi.fn() };
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
  usePathname: () => "/en/review",
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

const queueItem: ReportListItem = {
  id: "report-id",
  human_ref: "SL-2026-00001",
  status: reportStatus.under_review,
  urgency: "critical",
  summary: "Unprotected floor opening",
  location_text: "Level 14, Block C",
  created_at: new Date().toISOString(),
  thumbnail_caption: "Floor opening",
  thumbnail_url: "https://project.example/photo.jpg?token=signed",
  thumbnail_url_expires_at: new Date(Date.now() + 600_000).toISOString(),
  rework_count: 2,
};

function renderQueue(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <ReviewQueue requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("ReviewQueue", () => {
  beforeEach(() => {
    vi.mocked(listReports).mockReset();
    vi.mocked(listReports).mockResolvedValue({ items: [queueItem], next_cursor: null });
  });
  afterEach(cleanup);

  it("loads under-review reports and renders the required row fields", async () => {
    renderQueue();

    expect(await screen.findByText(queueItem.summary)).toBeTruthy();
    expect(screen.getByText(queueItem.human_ref)).toBeTruthy();
    expect(screen.getByText(queueItem.location_text!)).toBeTruthy();
    expect(screen.getByRole("img", { name: queueItem.thumbnail_caption! })).toBeTruthy();
    expect(screen.getAllByText(en["urgency.critical"])).toHaveLength(2);
    expect(screen.getAllByText(en["status.under_review"])).toHaveLength(2);
    expect(screen.getByText("Rework 2")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: new RegExp(queueItem.summary) })
        .getAttribute("href"),
    ).toBe(`/${defaultLocale}/review/${queueItem.id}`);
    expect(listReports).toHaveBeenCalledWith(
      { status: reportStatus.under_review, urgency: undefined, q: undefined, cursor: undefined },
      "test-token",
    );
  });

  it("offers every generated status and refetches after filtering", async () => {
    renderQueue();
    await screen.findByText(queueItem.summary);
    const user = userEvent.setup();
    const filter = screen.getByRole("combobox", { name: en["review.queue.statusFilter"] });

    expect(filter.querySelectorAll("option")).toHaveLength(reportStatuses.length + 1);
    await user.selectOptions(filter, reportStatus.submitted);

    await waitFor(() =>
      expect(listReports).toHaveBeenLastCalledWith(
        { status: reportStatus.submitted, urgency: undefined, q: undefined, cursor: undefined },
        "test-token",
      ),
    );
  });

  it("continues from the server cursor instead of using an offset", async () => {
    vi.mocked(listReports)
      .mockResolvedValueOnce({ items: [queueItem], next_cursor: "opaque-next" })
      .mockResolvedValueOnce({
        items: [{ ...queueItem, id: "report-two", human_ref: "SL-2026-00002" }],
        next_cursor: null,
      });
    renderQueue();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: en["review.queue.loadMore"] }));

    expect(await screen.findByText("SL-2026-00002")).toBeTruthy();
    expect(listReports).toHaveBeenLastCalledWith(
      {
        status: reportStatus.under_review,
        urgency: undefined,
        q: undefined,
        cursor: "opaque-next",
      },
      "test-token",
    );
  });

  it("renders the queue controls and status in Simplified Chinese", async () => {
    renderQueue(locales[1]);

    expect(await screen.findByText(zh["review.queue.title"])).toBeTruthy();
    expect(screen.getAllByText(zh["status.under_review"])).toHaveLength(2);
    expect(screen.getAllByText(zh["urgency.critical"])).toHaveLength(2);
  });
});
