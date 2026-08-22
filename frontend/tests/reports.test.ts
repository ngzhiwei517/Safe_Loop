import type { SupabaseClient } from "@supabase/supabase-js";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { defaultLocale } from "../lib/locales";
import { fileReport, listReports, type NewReportInput } from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));

const input: NewReportInput = {
  description_original: "Loose edge protection",
  lang_original: defaultLocale,
  location_text: "Level 6",
  activity: "Material delivery",
  level_or_zone: null,
  grid_ref: null,
  is_confidential: false,
  input_mode: "typed",
};

describe("fileReport", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("creates the draft before transitioning it to submitted", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ id: "report-id" })
      .mockResolvedValueOnce({
        id: "report-id",
        human_ref: "SL-2026-00001",
        status: reportStatus.submitted,
      });

    await expect(fileReport(input, "test-token")).resolves.toMatchObject({
      status: reportStatus.submitted,
    });
    expect(apiFetch).toHaveBeenNthCalledWith(1, "/reports", "test-token", {
      method: "POST",
      body: JSON.stringify(input),
    });
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      "/reports/report-id/transition",
      "test-token",
      {
        method: "POST",
        body: JSON.stringify({ target: reportStatus.submitted }),
      },
    );
  });

  it("uploads and registers a selected photo before submission", async () => {
    const upload = vi.fn(async () => ({ data: {}, error: null }));
    const client = {
      storage: {
        from: () => ({
          upload,
          remove: vi.fn(async () => ({ data: [], error: null })),
        }),
      },
    } as unknown as SupabaseClient;
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ id: "report-id" })
      .mockResolvedValueOnce({ id: "media-id" })
      .mockResolvedValueOnce({
        id: "report-id",
        human_ref: "SL-2026-00001",
        status: reportStatus.submitted,
      });

    await fileReport(input, "test-token", {
      client,
      file: new File(["photo"], "hazard.jpg", { type: "image/jpeg" }),
      userId: "reporter-id",
      caption: "Loose edge protection",
      downscale: async (file) => file,
    });

    expect(apiFetch).toHaveBeenCalledTimes(3);
    expect(vi.mocked(apiFetch).mock.calls[1][0]).toBe("/reports/report-id/media");
    expect(vi.mocked(apiFetch).mock.calls[2][0]).toBe("/reports/report-id/transition");
    expect(vi.mocked(apiFetch).mock.invocationCallOrder[0]).toBeLessThan(
      upload.mock.invocationCallOrder[0],
    );
    expect(upload.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(apiFetch).mock.invocationCallOrder[2],
    );
  });

  it("passes every queue filter through one keyset-paginated request", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [], next_cursor: null });

    await listReports(
      {
        status: reportStatus.under_review,
        urgency: "critical",
        assignee: "00000000-0000-0000-0000-000000000004",
        q: "Tower A",
        cursor: "opaque-cursor",
        limit: 25,
      },
      "test-token",
    );

    expect(apiFetch).toHaveBeenCalledWith(
      "/reports?status=under_review&urgency=critical&assignee=00000000-0000-0000-0000-000000000004&q=Tower+A&cursor=opaque-cursor&limit=25",
      "test-token",
    );
  });
});
