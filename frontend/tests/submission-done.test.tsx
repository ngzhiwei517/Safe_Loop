import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SubmissionDone } from "../components/reports/SubmissionDone";
import { defaultLocale } from "../lib/locales";
import { mediaPhase } from "../lib/media";
import { getReport } from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";
import en from "../messages/en.json";

vi.mock("../lib/reports", () => ({ getReport: vi.fn() }));
vi.mock("../lib/supabase/browser", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "test-token" } },
      }),
    },
  }),
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

describe("SubmissionDone", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(getReport).mockReset();
  });
  afterEach(cleanup);

  it("renders private report media from the backend signed URL", async () => {
    vi.mocked(getReport).mockResolvedValue({
      id: "report-id",
      human_ref: "SL-2026-00001",
      status: reportStatus.submitted,
      available_transitions: [],
      media: [
        {
          id: "media-id",
          storage_path: "private/path.jpg",
          mime_type: "image/jpeg",
          phase: mediaPhase.original,
          caption: "Loose guardrail",
          signed_url: "https://project.example/storage/photo.jpg?token=signed",
          signed_url_expires_at: "2026-08-22T09:10:00Z",
        },
      ],
    });

    render(
      <NextIntlClientProvider locale={defaultLocale} messages={expand(en)}>
        <SubmissionDone id="report-id" locale={defaultLocale} />
      </NextIntlClientProvider>,
    );

    const image = await screen.findByRole("img", { name: "Loose guardrail" });
    expect(image.getAttribute("src")).toContain("token=signed");
    expect(getReport).toHaveBeenCalledWith("report-id", "test-token");
  });
});
