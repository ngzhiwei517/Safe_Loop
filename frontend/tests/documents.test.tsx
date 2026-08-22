import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentsPage } from "../components/documents/DocumentsPage";
import {
  approveDocument,
  listDocuments,
  retireDocument,
  uploadDocument,
  type CorpusDocument,
} from "../lib/documents";
import { defaultLocale, locales } from "../lib/locales";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";

vi.mock("../lib/documents", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/documents")>();
  return {
    ...original,
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    approveDocument: vi.fn(),
    retireDocument: vi.fn(),
  };
});
vi.mock("../lib/notifications", () => ({ listNotifications: vi.fn(async () => ({ unread_count: 0, priority_unread_count: 0, items: [] })) }));
vi.mock("../lib/alerts", () => ({ listAlerts: vi.fn(async () => []) }));
vi.mock("../lib/supabase/browser", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "test-token" } } }) },
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/documents",
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

const pending: CorpusDocument = {
  id: "document-three",
  title: "Work at height method statement",
  doc_ref: "WSH-MS-014",
  revision: "3",
  is_approved: false,
  approval_state: "pending",
  effective_from: "2026-07-01T00:00:00Z",
  approved_at: null,
  retired_at: null,
  chunk_count: 6,
  cited_by_drafts: 0,
  created_at: "2026-08-20T00:00:00Z",
};

const approved: CorpusDocument = {
  ...pending,
  id: "document-two",
  revision: "2",
  is_approved: true,
  approval_state: "approved",
  approved_at: "2026-06-01T00:00:00Z",
  cited_by_drafts: 24,
};

function renderDocuments(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <DocumentsPage requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("DocumentsPage", () => {
  beforeEach(() => {
    vi.mocked(listDocuments).mockReset();
    vi.mocked(uploadDocument).mockReset();
    vi.mocked(approveDocument).mockReset();
    vi.mocked(retireDocument).mockReset();
    vi.mocked(listDocuments).mockResolvedValue([pending, approved]);
    vi.mocked(approveDocument).mockResolvedValue({ ...pending, is_approved: true, approval_state: "approved" });
    vi.mocked(retireDocument).mockResolvedValue({ ...approved, is_approved: false, approval_state: "retired" });
  });
  afterEach(cleanup);

  it("shows exact revisions, approval state, effective date, and citation count", async () => {
    renderDocuments();

    expect(await screen.findAllByText(pending.title)).toHaveLength(2);
    expect(screen.getByText(en["documents.state.pending"])).toBeTruthy();
    expect(screen.getByText(en["documents.state.approved"])).toBeTruthy();
    expect(screen.getByText("Cited by 24 AI drafts")).toBeTruthy();
    expect(screen.getByText(/WSH-MS-014 · rev 3 · effective/)).toBeTruthy();
  });

  it("approves one selected revision explicitly", async () => {
    renderDocuments();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Approve rev 3" }));

    await waitFor(() => expect(approveDocument).toHaveBeenCalledWith("document-three", "test-token"));
    expect(listDocuments).toHaveBeenCalledTimes(2);
    expect(retireDocument).not.toHaveBeenCalled();
  });

  it("renders the corpus controls in Simplified Chinese", async () => {
    renderDocuments(locales[1]);

    expect(await screen.findByText(zh["documents.title"])).toBeTruthy();
    expect(screen.getByRole("button", { name: "批准第 3 版" })).toBeTruthy();
    expect(screen.getByText("已有 24 个 AI 草稿引用")).toBeTruthy();
  });
});
