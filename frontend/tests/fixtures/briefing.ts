import type { ManagedBriefing } from "../../lib/briefings";

export const briefingFixture: ManagedBriefing = {
  id: "briefing-one",
  report_id: "report-one",
  human_ref: "SL-2026-00042",
  report_status: "lesson_drafted",
  version: 1,
  body: {
    en: "Secure each opening before work starts.",
    "zh-CN": "开工前固定每个洞口。",
  },
  status: "draft",
  target_activity: "Formwork",
  target_location: "Level 6",
  valid_from: "2026-08-24T00:00:00+08:00",
  valid_to: "2026-09-24T23:59:59+08:00",
  qr_token: null,
  approved_by: null,
  approved_by_name: null,
  approved_at: null,
  created_at: "2026-08-24T00:00:00Z",
  question_count: 3,
  available_transitions: [
    {
      event: "publish_lesson",
      target: "lesson_published",
      requires_reason: false,
    },
  ],
};
