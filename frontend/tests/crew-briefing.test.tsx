import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CrewBriefingPage } from "../components/learning/CrewBriefingPage";
import { submitQuizAnswer, type PublicBriefing } from "../lib/briefings";
import { defaultLocale, locales } from "../lib/locales";
import { createClient } from "../lib/supabase/browser";
import en from "../messages/en.json";
import zh from "../messages/zh-CN.json";
import { publicBriefingFixture } from "./fixtures/learning";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("../lib/briefings", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/briefings")>();
  return { ...original, submitQuizAnswer: vi.fn() };
});
vi.mock("../lib/supabase/browser", () => ({ createClient: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/b/public-token",
  useRouter: () => ({ replace, refresh }),
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

function renderCrew(
  locale = defaultLocale,
  briefing: PublicBriefing | null = publicBriefingFixture,
) {
  return render(
    <NextIntlClientProvider
      locale={locale}
      messages={expand(locale === defaultLocale ? en : zh)}
    >
      <CrewBriefingPage
        requestedLocale={locale}
        token="public-token"
        briefing={briefing}
      />
    </NextIntlClientProvider>,
  );
}

describe("CrewBriefingPage", () => {
  beforeEach(() => {
    replace.mockReset();
    refresh.mockReset();
    vi.mocked(createClient).mockReset();
    vi.mocked(createClient).mockReturnValue({
      auth: { getSession: async () => ({ data: { session: null } }) },
    } as ReturnType<typeof createClient>);
    vi.mocked(submitQuizAnswer).mockReset();
    vi.mocked(submitQuizAnswer).mockResolvedValue({
      response_id: "response-one",
      is_correct: true,
      correct_option: 0,
    });
  });
  afterEach(cleanup);

  it("shows the three field-check sections and immediate server feedback", async () => {
    renderCrew();
    expect(screen.getByText(en["crew.section.whatHappened"])).toBeTruthy();
    expect(screen.getByText(en["crew.section.whyMatters"])).toBeTruthy();
    expect(screen.getByText(en["crew.section.doDifferently"])).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Before work starts" }));

    expect(await screen.findByText(en["crew.quiz.correct"])).toBeTruthy();
    expect(screen.getByText("Secure it before work starts.")).toBeTruthy();
    expect(submitQuizAnswer).toHaveBeenCalledWith(
      "public-token",
      "question-one",
      0,
      undefined,
    );
  });

  it("renders the inactive page in Simplified Chinese", () => {
    renderCrew(locales[1], null);
    expect(screen.getByText(zh["crew.inactive.title"])).toBeTruthy();
    expect(screen.getByText(zh["crew.inactive.detail"])).toBeTruthy();
  });

  it("changes a public URL and cookie without looking up an account", async () => {
    renderCrew();
    vi.mocked(createClient).mockClear();

    await userEvent.click(screen.getByRole("button", { name: en["app.languageChinese"] }));

    expect(createClient).not.toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith("/zh-CN/b/public-token");
    expect(document.cookie).toContain("safeloop-locale=zh-CN");
  });
});
