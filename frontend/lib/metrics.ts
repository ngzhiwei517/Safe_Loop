import { apiFetch } from "./api";
import type { LocaleText } from "./briefings";
import type { ReportStatus } from "./stateMachine";

export type QuestionPerformance = {
  question_id: string;
  briefing_id: string;
  position: number;
  question: LocaleText;
  first_attempt_count: number;
  first_attempt_correct_count: number;
  first_attempt_wrong_count: number;
  first_attempt_pass_rate: number | null;
};

export type ResponsibleRework = {
  profile_id: string;
  display_name: string;
  action_count: number;
  reworked_action_count: number;
  rework_rate: number;
};

export type RepeatHazardCluster = {
  category: string;
  location: string;
  report_count: number;
  recurrence_count: number;
  first_closed_at: string;
  latest_closed_at: string;
  responsible_rework: ResponsibleRework[];
};

export type MetricsSummary = {
  open_by_status: Partial<Record<ReportStatus, number>>;
  overdue_count: number;
  rework_rate: number;
  median_verification_cycles_to_close: number | null;
  median_submitted_to_under_review_seconds: number | null;
  median_submitted_to_action_assigned_seconds: number | null;
  median_action_assigned_to_verified_closed_seconds: number | null;
  reviewer_correction_rate: number;
  published_briefing_count: number;
  crew_reach: number;
  anonymous_quiz_response_count: number;
  first_attempt_count: number;
  first_attempt_pass_rate: number | null;
  question_performance: QuestionPerformance[];
  questions_most_often_wrong: QuestionPerformance[];
  repeat_hazard_window_days: number;
  repeat_hazards: RepeatHazardCluster[];
};

export function getMetricsSummary(accessToken: string): Promise<MetricsSummary> {
  return apiFetch<MetricsSummary>("/metrics/summary", accessToken);
}
