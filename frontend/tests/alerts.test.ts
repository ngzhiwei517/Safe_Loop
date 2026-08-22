import { describe, expect, it } from "vitest";

import { reporterAlertCopyKey, type AlertItem } from "../lib/alerts";

function alert(overrides: Partial<AlertItem> = {}): AlertItem {
  return {
    id: "alert-id",
    report_id: "report-id",
    human_ref: "SL-2026-00001",
    description_original: "Hazard",
    raised_by: "reporter-id",
    raised_at: "2026-08-22T08:00:00Z",
    location_text: "Level 6",
    acknowledged_by: null,
    acknowledged_by_name: null,
    acknowledged_at: null,
    escalated_at: null,
    resolution_note: null,
    ...overrides,
  };
}

describe("reporterAlertCopyKey", () => {
  it("cannot return acknowledged copy before a named acknowledgement", () => {
    expect(reporterAlertCopyKey(alert())).toBe("alert.reporter.sent");
    expect(
      reporterAlertCopyKey(alert({ acknowledged_at: "2026-08-22T08:01:00Z" })),
    ).toBe("alert.reporter.sent");
    expect(
      reporterAlertCopyKey(alert({ acknowledged_by_name: "Reviewer Lim" })),
    ).toBe("alert.reporter.sent");
  });

  it("shows escalation while no human has acknowledged", () => {
    expect(
      reporterAlertCopyKey(alert({ escalated_at: "2026-08-22T08:05:00Z" })),
    ).toBe("alert.reporter.escalated");
  });

  it("uses named acknowledged copy only after acknowledgement", () => {
    expect(
      reporterAlertCopyKey(
        alert({
          acknowledged_at: "2026-08-22T08:01:00Z",
          acknowledged_by: "reviewer-id",
          acknowledged_by_name: "Reviewer Lim",
        }),
      ),
    ).toBe("alert.reporter.acknowledged");
  });
});
