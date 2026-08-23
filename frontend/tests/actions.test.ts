import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  listOpenActions,
  submitActionEvidence,
  type OpenAction,
} from "../lib/actions";
import { apiFetch } from "../lib/api";
import { listReports } from "../lib/reports";
import { reportStatus } from "../lib/stateMachine";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));
vi.mock("../lib/reports", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/reports")>();
  return { ...original, listReports: vi.fn() };
});

function action(id: string, due: string, reworkCount = 0): OpenAction {
  return {
    id: `report-${id}`,
    human_ref: `SL-2026-${id}`,
    status: reportStatus.action_assigned,
    urgency: "medium",
    summary: "Loose guardrail",
    location_text: "Level 6",
    created_at: "2026-08-20T00:00:00Z",
    thumbnail_caption: null,
    thumbnail_url: null,
    thumbnail_url_expires_at: null,
    action_id: `action-${id}`,
    action_text: "Secure the guardrail.",
    action_status: "assigned",
    action_due_at: due,
    completed_note: null,
    action_submitted_at: null,
    rework_count: reworkCount,
    rework_attention: reworkCount >= 2,
    sent_back_unresolved: reworkCount > 0,
    deficiency_reason: reworkCount ? "Anchor is still loose." : null,
    deficiency_notes: null,
    deficiency_created_at: null,
    deficiency_reviewer_name: null,
    previous_evidence: [],
  };
}

describe("technician actions API", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
    vi.mocked(listReports).mockReset();
  });

  it("loads my assigned work and pins returned work before due-date order", async () => {
    vi.mocked(listReports).mockResolvedValue({
      items: [
        action("00003", "2026-08-30T00:00:00Z"),
        action("00002", "2026-08-29T00:00:00Z", 1),
        action("00001", "2026-08-28T00:00:00Z"),
      ],
      next_cursor: null,
      counts: { overdue: 0, rework: 0 },
    });

    const result = await listOpenActions("test-token");

    expect(listReports).toHaveBeenCalledWith(
      {
        status: reportStatus.action_assigned,
        assignee: "me",
        limit: 100,
        cursor: undefined,
      },
      "test-token",
    );
    expect(result.map((item) => item.action_id)).toEqual([
      "action-00002",
      "action-00001",
      "action-00003",
    ]);
  });

  it("loads every open-action page before applying due-date order", async () => {
    vi.mocked(listReports)
      .mockResolvedValueOnce({
        items: [action("00002", "2026-08-30T00:00:00Z")],
        next_cursor: "next-page",
        counts: { overdue: 0, rework: 0 },
      })
      .mockResolvedValueOnce({
        items: [action("00001", "2026-08-28T00:00:00Z")],
        next_cursor: null,
        counts: { overdue: 0, rework: 0 },
      });

    const result = await listOpenActions("test-token");

    expect(listReports).toHaveBeenNthCalledWith(
      2,
      {
        status: reportStatus.action_assigned,
        assignee: "me",
        limit: 100,
        cursor: "next-page",
      },
      "test-token",
    );
    expect(result.map((item) => item.action_id)).toEqual([
      "action-00001",
      "action-00002",
    ]);
  });

  it("submits the note and registered evidence ids to the atomic endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ status: reportStatus.action_submitted });
    const input = {
      completed_note: "Guardrail secured.",
      media_ids: ["media-id"],
    };

    await submitActionEvidence("report-id", "action-id", input, "test-token");

    expect(apiFetch).toHaveBeenCalledWith(
      "/reports/report-id/actions/action-id/submit",
      "test-token",
      { method: "POST", body: JSON.stringify(input) },
    );
  });
});
