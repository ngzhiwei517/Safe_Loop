import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ActionsPage } from "../components/actions/ActionsPage";
import {
  listOpenActions,
  submitActionEvidence,
  type OpenAction,
} from "../lib/actions";
import { defaultLocale, locales } from "../lib/locales";
import { reportStatus } from "../lib/stateMachine";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";

vi.mock("../lib/actions", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/actions")>();
  return {
    ...original,
    listOpenActions: vi.fn(),
    submitActionEvidence: vi.fn(),
  };
});
vi.mock("../lib/notifications", () => ({
  listNotifications: vi.fn(async () => ({
    unread_count: 0,
    priority_unread_count: 0,
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
      getUser: async () => ({ data: { user: { id: "responsible-id" } } }),
    },
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/actions",
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

const returnedAction: OpenAction = {
  id: "report-id",
  human_ref: "SL-2026-00042",
  status: reportStatus.action_assigned,
  urgency: "high",
  summary: "Loose edge guardrail",
  location_text: "Level 6 east edge",
  created_at: "2026-08-20T00:00:00Z",
  thumbnail_caption: null,
  thumbnail_url: null,
  thumbnail_url_expires_at: null,
  action_id: "action-id",
  action_text: "Secure every guardrail anchor before work resumes.",
  action_status: "assigned",
  action_due_at: "2099-08-25T00:00:00Z",
  completed_note: "Tightened the upper anchor.",
  action_submitted_at: "2026-08-22T00:00:00Z",
  rework_count: 1,
  rework_attention: false,
  deficiency_reason: "The lower anchor still moves when pulled.",
  deficiency_notes: null,
  deficiency_created_at: "2026-08-22T01:00:00Z",
  deficiency_reviewer_name: "SO Lim",
  previous_evidence: [
    {
      id: "media-id",
      caption: null,
      created_at: "2026-08-22T00:00:00Z",
      signed_url: "https://project.example/evidence.jpg?token=signed",
      signed_url_expires_at: "2099-08-22T00:10:00Z",
    },
  ],
};

function renderActions(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <ActionsPage requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("ActionsPage", () => {
  beforeEach(() => {
    vi.mocked(listOpenActions).mockReset();
    vi.mocked(submitActionEvidence).mockReset();
    vi.mocked(listOpenActions).mockResolvedValue([returnedAction]);
    vi.mocked(submitActionEvidence).mockResolvedValue({
      report_id: returnedAction.id,
      action_id: returnedAction.action_id,
      status: reportStatus.action_submitted,
      completed_note: "Lower anchor replaced.",
      submitted_at: "2026-08-23T00:00:00Z",
      media_ids: [],
    });
  });
  afterEach(cleanup);

  it("shows the returned deficiency and previous evidence before the action", async () => {
    renderActions();

    const deficiency = await screen.findByText(returnedAction.deficiency_reason!);
    const instruction = screen.getByText(returnedAction.action_text);
    expect(
      deficiency.compareDocumentPosition(instruction) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole("img", { name: en["action.previous.photoAlt"] }),
    ).toBeTruthy();
  });

  it("submits a note from the phone view without requiring a photo", async () => {
    vi.mocked(listOpenActions)
      .mockResolvedValueOnce([returnedAction])
      .mockResolvedValueOnce([]);
    renderActions();
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: en["work.submit.again"] }),
    );
    await user.type(
      screen.getByRole("textbox", { name: en["work.submit.note"] }),
      "Lower anchor replaced.",
    );
    await user.click(
      screen.getByRole("button", { name: en["work.submit.send"] }),
    );

    await waitFor(() =>
      expect(submitActionEvidence).toHaveBeenCalledWith(
        returnedAction.id,
        returnedAction.action_id,
        { completed_note: "Lower anchor replaced.", media_ids: [] },
        "test-token",
      ),
    );
    expect(await screen.findByText(en["work.submit.successTitle"])).toBeTruthy();
  });

  it("renders the technician surface in Simplified Chinese", async () => {
    vi.mocked(listOpenActions).mockResolvedValue([]);
    renderActions(locales[1]);

    expect(await screen.findAllByText(zh["action.list.title"])).toHaveLength(2);
    expect(screen.getByText(zh["action.list.emptyTitle"])).toBeTruthy();
  });
});
