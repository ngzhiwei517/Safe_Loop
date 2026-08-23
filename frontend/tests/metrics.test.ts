import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { getMetricsSummary } from "../lib/metrics";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));

describe("metrics API", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("loads the authenticated summary endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ open_by_status: {} });

    await getMetricsSummary("test-token");

    expect(apiFetch).toHaveBeenCalledWith("/metrics/summary", "test-token");
  });
});
