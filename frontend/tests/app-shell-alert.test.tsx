import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "../components/ui/AppShell";
import en from "../messages/en.json";
import { listAlerts } from "../lib/alerts";
import { listNotifications } from "../lib/notifications";

const supabase = vi.hoisted(() => ({
  auth: {
    getSession: async () => ({
      data: { session: { access_token: "reviewer-token" } },
    }),
  },
}));

vi.mock("../lib/alerts", () => ({ listAlerts: vi.fn() }));
vi.mock("../lib/notifications", () => ({ listNotifications: vi.fn() }));
vi.mock("../lib/supabase/browser", () => ({ createClient: () => supabase }));

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

describe("AppShell urgent alerts", () => {
  afterEach(cleanup);

  it("puts an undismissable banner in front of a reviewer on the first poll", async () => {
    vi.mocked(listNotifications).mockResolvedValue({
      items: [],
      unread_count: 1,
      priority_unread_count: 0,
      unresolved_sent_back_count: 0,
    });
    vi.mocked(listAlerts).mockResolvedValue([
      {
        id: "alert-id",
        report_id: "report-id",
        human_ref: "SL-2026-00001",
        description_original: "Hazard",
        raised_by: "reporter-id",
        raised_at: "2026-08-22T08:00:00Z",
        location_text: "Level 6",
        acknowledged_by: null,
        acknowledged_by_name: null,
        acknowledged_at: null,
        escalated_at: null,
        resolution_note: null,
      },
    ]);

    render(
      <NextIntlClientProvider locale="en" messages={expand(en)}>
        <AppShell
          title={en["app.name"]}
          inboxHref="/en/inbox"
          inboxLabel={en["app.inbox"]}
          unreadCount={0}
          navItems={[]}
          activeHref="/en/review"
          pollStatus
          showUrgentAlerts
          alertsHref="/en/alerts"
        >
          <span />
        </AppShell>
      </NextIntlClientProvider>,
    );

    expect(
      await screen.findByText(en["alert.banner.title"]),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: en["alert.banner.open"] }).getAttribute("href"),
    ).toBe("/en/alerts");
    expect(screen.queryByRole("button", { name: /dismiss/i })).toBeNull();
    await waitFor(() => expect(listAlerts).toHaveBeenCalledWith("reviewer-token"));
  });
});
