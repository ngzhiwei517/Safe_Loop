import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch, publicApiFetch } from "../lib/api";
import {
  getPublicBriefing,
  getQuizProgress,
  listLearningBriefings,
  submitQuizAnswer,
} from "../lib/briefings";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn(), publicApiFetch: vi.fn() }));

describe("learning API client", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
    vi.mocked(publicApiFetch).mockReset();
    vi.mocked(apiFetch).mockResolvedValue([]);
    vi.mocked(publicApiFetch).mockResolvedValue({});
  });

  it("keeps public reads anonymous and only attaches a token when one exists", async () => {
    await getPublicBriefing("public token");
    await submitQuizAnswer("public token", "question-id", 2);
    await submitQuizAnswer("public token", "question-id", 1, "access-token");
    await getQuizProgress("public token", "access-token");
    await listLearningBriefings("access-token");

    expect(vi.mocked(publicApiFetch).mock.calls).toEqual([
      ["/briefings/public%20token"],
      [
        "/briefings/public%20token/quiz",
        {
          method: "POST",
          body: JSON.stringify({ question_id: "question-id", selected_option: 2 }),
        },
        undefined,
      ],
      [
        "/briefings/public%20token/quiz",
        {
          method: "POST",
          body: JSON.stringify({ question_id: "question-id", selected_option: 1 }),
        },
        "access-token",
      ],
    ]);
    expect(vi.mocked(apiFetch).mock.calls).toEqual([
      ["/briefings/public%20token/progress", "access-token"],
      ["/briefings", "access-token"],
    ]);
  });
});
