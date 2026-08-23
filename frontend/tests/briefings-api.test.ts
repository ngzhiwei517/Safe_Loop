import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import {
  getManagedBriefing,
  listManagedBriefings,
  publishManagedBriefing,
  saveManagedBriefing,
  type BriefingEditPayload,
} from "../lib/briefings";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));

describe("briefing API client", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("uses the reviewer management routes", async () => {
    vi.mocked(apiFetch).mockResolvedValue({});
    const payload: BriefingEditPayload = {
      body: { en: "English", "zh-CN": "中文" },
      target_activity: "Formwork",
      target_location: "Level 6",
      valid_from: "2026-08-24",
      valid_to: "2026-09-24",
      quiz_questions: [],
    };

    await listManagedBriefings("token");
    await getManagedBriefing("briefing-id", "token");
    await saveManagedBriefing("briefing-id", payload, "token");
    await publishManagedBriefing("briefing-id", "token");

    expect(vi.mocked(apiFetch).mock.calls).toEqual([
      ["/briefings/manage", "token"],
      ["/briefings/manage/briefing-id", "token"],
      [
        "/briefings/manage/briefing-id",
        "token",
        { method: "PATCH", body: JSON.stringify(payload) },
      ],
      [
        "/briefings/manage/briefing-id/publish",
        "token",
        { method: "POST" },
      ],
    ]);
  });
});
