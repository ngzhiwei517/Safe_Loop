import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { defaultLocale } from "../lib/locales";
import { fileReport, type NewReportInput } from "../lib/reports";
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
  beforeEach(() => vi.mocked(apiFetch).mockReset());

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
});
