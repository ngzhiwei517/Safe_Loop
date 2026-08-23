import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BriefingEditorPage } from "../components/briefings/BriefingEditorPage";
import {
  getManagedBriefing,
  publishManagedBriefing,
  saveManagedBriefing,
  type ManagedBriefing,
} from "../lib/briefings";
import { defaultLocale, locales } from "../lib/locales";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";
import { briefingFixture } from "./fixtures/briefing";

const replace = vi.fn();

vi.mock("../lib/briefings", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/briefings")>();
  return {
    ...original,
    getManagedBriefing: vi.fn(),
    saveManagedBriefing: vi.fn(),
    publishManagedBriefing: vi.fn(),
  };
});
vi.mock("../lib/briefingQr", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/briefingQr")>();
  return {
    ...original,
    qrDataUrl: vi.fn(async () => "data:image/png;base64,cXJjb2Rl"),
    downloadNoticeboardPng: vi.fn(async () => undefined),
    downloadNoticeboardPdf: vi.fn(async () => undefined),
  };
});
vi.mock("../lib/notifications", () => ({ listNotifications: vi.fn(async () => ({ unread_count: 0, priority_unread_count: 0, unresolved_sent_back_count: 0, items: [] })) }));
vi.mock("../lib/alerts", () => ({ listAlerts: vi.fn(async () => []) }));
vi.mock("../lib/supabase/browser", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "test-token" } } }) },
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/briefings/briefing-one",
  useRouter: () => ({ replace, refresh: vi.fn() }),
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

const questions = Array.from({ length: 3 }, (_, index) => ({
  id: `question-${index + 1}`,
  position: index + 1,
  question: { en: `Question ${index + 1}?`, "zh-CN": `问题 ${index + 1}？` },
  explanation: { en: `Explanation ${index + 1}.`, "zh-CN": `解释 ${index + 1}。` },
  options: Array.from({ length: 4 }, (__, option) => ({
    en: `Option ${option + 1}`,
    "zh-CN": `选项 ${option + 1}`,
  })),
  correct_option: 0,
  created_at: "2026-08-24T00:00:00Z",
}));

const editableFixture: ManagedBriefing = {
  ...briefingFixture,
  quiz_questions: questions,
};

function renderEditor(locale = defaultLocale) {
  const messages = locale === defaultLocale ? en : zh;
  return render(
    <NextIntlClientProvider locale={locale} messages={expand(messages)}>
      <BriefingEditorPage id={editableFixture.id} requestedLocale={locale} />
    </NextIntlClientProvider>,
  );
}

describe("BriefingEditorPage", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.mocked(getManagedBriefing).mockReset();
    vi.mocked(saveManagedBriefing).mockReset();
    vi.mocked(publishManagedBriefing).mockReset();
    vi.mocked(getManagedBriefing).mockResolvedValue(editableFixture);
    vi.mocked(saveManagedBriefing).mockResolvedValue(editableFixture);
    vi.mocked(publishManagedBriefing).mockResolvedValue({
      ...editableFixture,
      status: "published",
      report_status: "lesson_published",
      qr_token: "unguessable-token",
      approved_by: "reviewer-id",
      approved_by_name: "Safety reviewer",
      approved_at: "2026-08-24T08:00:00Z",
      available_transitions: [],
    });
  });
  afterEach(cleanup);

  it("pairs every English and Chinese field and publishes the saved draft", async () => {
    renderEditor();
    const user = userEvent.setup();

    const englishBody = await screen.findByRole("textbox", { name: "Body · English" });
    const chineseBody = screen.getByRole("textbox", { name: "Body · 简体中文" });
    expect((englishBody as HTMLTextAreaElement).value).toBe(editableFixture.body.en);
    expect((chineseBody as HTMLTextAreaElement).value).toBe(editableFixture.body["zh-CN"]);
    expect(screen.getAllByText(en["briefings.editor.questionHelp"])).toHaveLength(3);

    await user.clear(chineseBody);
    await user.type(chineseBody, "审核员修改后的中文内容。 ");
    await user.click(screen.getByRole("button", { name: en["briefings.editor.publish"] }));

    await waitFor(() => expect(saveManagedBriefing).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(saveManagedBriefing).mock.calls[0][1];
    expect(payload.body["zh-CN"]).toBe("审核员修改后的中文内容。 ");
    await waitFor(() => expect(publishManagedBriefing).toHaveBeenCalledWith(
      editableFixture.id,
      "test-token",
    ));
    expect(await screen.findByText(en["briefings.qr.title"])).toBeTruthy();
  });

  it("forks a published version before saving reviewer edits", async () => {
    const published = {
      ...editableFixture,
      status: "published" as const,
      report_status: "lesson_published",
      qr_token: "first-token",
      approved_by: "reviewer-id",
      approved_by_name: "Safety reviewer",
      approved_at: "2026-08-24T08:00:00Z",
      available_transitions: [],
    };
    const revision = {
      ...editableFixture,
      id: "briefing-two",
      version: 2,
      report_status: "lesson_published",
      available_transitions: [
        {
          event: "republish_lesson",
          target: "lesson_published",
          requires_reason: false,
        },
      ],
    };
    vi.mocked(getManagedBriefing).mockResolvedValue(published);
    vi.mocked(saveManagedBriefing).mockResolvedValue(revision);
    renderEditor();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: en["briefings.editor.createDraft"] }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/en/briefings/briefing-two"));
    expect(publishManagedBriefing).not.toHaveBeenCalled();
  });

  it("hides Publish when the server returns no available transition", async () => {
    vi.mocked(getManagedBriefing).mockResolvedValue({
      ...editableFixture,
      available_transitions: [],
    });
    renderEditor();

    await screen.findByText(en["briefings.editor.bodyTitle"]);
    expect(screen.queryByRole("button", { name: en["briefings.editor.publish"] })).toBeNull();
  });

  it("renders reviewer controls in Simplified Chinese", async () => {
    renderEditor(locales[1]);
    expect(await screen.findByRole("button", { name: zh["briefings.editor.publish"] })).toBeTruthy();
    expect(screen.getByText(zh["briefings.editor.bodyTitle"])).toBeTruthy();
  });
});
