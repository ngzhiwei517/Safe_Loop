import { apiFetch } from "./api";
import type { ReportStatus } from "./stateMachine";

export type MetricsSummary = {
  open_by_status: Partial<Record<ReportStatus, number>>;
  overdue_count: number;
  rework_rate: number;
  median_verification_cycles_to_close: number | null;
  median_submitted_to_under_review_seconds: number | null;
  median_submitted_to_action_assigned_seconds: number | null;
  median_action_assigned_to_verified_closed_seconds: number | null;
  reviewer_correction_rate: number;
};

export function getMetricsSummary(accessToken: string): Promise<MetricsSummary> {
  return apiFetch<MetricsSummary>("/metrics/summary", accessToken);
}
