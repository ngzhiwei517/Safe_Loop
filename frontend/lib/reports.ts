import { apiFetch } from "./api";
import type { Locale } from "./locales";
import { uploadReportPhoto, type MediaPhase, type ReportPhotoUpload } from "./media";
import { reportStatus, type ReportStatus } from "./stateMachine";

export const urgencyLevels = ["low", "medium", "high", "critical"] as const;
export type Urgency = (typeof urgencyLevels)[number];

export type NewReportInput = {
  description_original: string;
  lang_original: Locale;
  location_text: string;
  activity: string;
  level_or_zone: string | null;
  grid_ref: string | null;
  is_confidential: boolean;
  input_mode: "typed";
};

type CreatedReport = { id: string };
export type SubmittedReport = { id: string; human_ref: string; status: typeof reportStatus.submitted };

export type ReportMedia = {
  id: string;
  storage_path: string;
  mime_type: string;
  phase: MediaPhase;
  caption: string | null;
  signed_url: string;
  signed_url_expires_at: string;
};

export type AvailableTransition = {
  event: string;
  target: ReportStatus;
  requires_reason: boolean;
  review_decision?: ReviewDecision;
};

export const reviewDecisions = ["approve", "request_info", "escalate", "reject"] as const;
export type ReviewDecision = (typeof reviewDecisions)[number];

export type ReviewInput = {
  decision: ReviewDecision;
  target: ReportStatus;
  reason?: string;
  corrected_category?: string;
  corrected_urgency?: Urgency;
  corrected_action?: string;
  correction_reason?: string;
  assignee_id?: string;
  due_at?: string;
};

export type ReviewResult = {
  review_id: string;
  report_id: string;
  status: ReportStatus;
  assignment_id: string | null;
  corrective_action_id: string | null;
};

export type AiDraft = {
  id: string;
  version: number;
  observed_facts: string[];
  assumptions: string[];
  missing_information: string[];
  proposed_category: string | null;
  proposed_urgency: Urgency | null;
  suggested_owner_role: string | null;
  suggested_action: string | null;
  confidence: number | null;
  needs_escalation: boolean;
  escalation_reason: string | null;
  citations: Record<string, unknown>[];
  validation: "valid" | "invalid" | null;
  validation_errors: string[];
  created_at: string;
};

export type ReportDetail = {
  id: string;
  human_ref: string;
  status: ReportStatus;
  urgency: Urgency;
  lang_original: Locale;
  description_original: string;
  description_en: string | null;
  location_text: string | null;
  activity: string | null;
  level_or_zone: string | null;
  grid_ref: string | null;
  created_at: string;
  media: ReportMedia[];
  latest_draft: AiDraft | null;
  available_transitions: AvailableTransition[];
};

export type ReportListItem = {
  id: string;
  human_ref: string;
  status: ReportStatus;
  urgency: Urgency;
  summary: string;
  location_text: string | null;
  created_at: string;
  thumbnail_caption: string | null;
  thumbnail_url: string | null;
  thumbnail_url_expires_at: string | null;
  rework_count: number;
};

export type ReportListPage = {
  items: ReportListItem[];
  next_cursor: string | null;
};

export type ReportListFilters = {
  status?: ReportStatus;
  urgency?: Urgency;
  assignee?: string;
  needsManualTriage?: boolean;
  q?: string;
  cursor?: string;
  limit?: number;
};

export type TimelineEntry = {
  id: string;
  event: string;
  actor_type: "human" | "ai" | "system";
  actor_role: "reporter" | "reviewer" | "responsible" | "crew" | "admin" | null;
  source: ReportStatus | null;
  target: ReportStatus | null;
  reason: string | null;
  created_at: string;
};

export async function fileReport(
  input: NewReportInput,
  accessToken: string,
  photo?: ReportPhotoUpload,
  existingDraftId?: string,
): Promise<SubmittedReport> {
  const created = existingDraftId
    ? await apiFetch<CreatedReport>(`/reports/${existingDraftId}`, accessToken, {
        method: "PATCH",
        body: JSON.stringify(input),
      })
    : await createReportDraft(input, accessToken);
  if (photo) {
    await uploadReportPhoto({
      ...photo,
      reportId: created.id,
      accessToken,
    });
  }
  return apiFetch<SubmittedReport>(`/reports/${created.id}/transition`, accessToken, {
    method: "POST",
    body: JSON.stringify({ target: reportStatus.submitted }),
  });
}

export function createReportDraft(
  input: NewReportInput,
  accessToken: string,
): Promise<CreatedReport> {
  return apiFetch<CreatedReport>("/reports", accessToken, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getReport(reportId: string, accessToken: string): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${reportId}`, accessToken);
}

export function listReports(filters: ReportListFilters, accessToken: string): Promise<ReportListPage> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.urgency) params.set("urgency", filters.urgency);
  if (filters.assignee) params.set("assignee", filters.assignee);
  if (filters.needsManualTriage) params.set("needs_manual_triage", "true");
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.cursor) params.set("cursor", filters.cursor);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return apiFetch<ReportListPage>(`/reports${query ? `?${query}` : ""}`, accessToken);
}

export function getTimeline(reportId: string, accessToken: string): Promise<TimelineEntry[]> {
  return apiFetch<TimelineEntry[]>(`/reports/${reportId}/timeline`, accessToken);
}

export function transitionReport(
  reportId: string,
  target: ReportStatus,
  accessToken: string,
  reason?: string,
): Promise<{ id: string; status: ReportStatus }> {
  return apiFetch<{ id: string; status: ReportStatus }>(
    `/reports/${reportId}/transition`,
    accessToken,
    {
      method: "POST",
      body: JSON.stringify({ target, reason }),
    },
  );
}

export function reviewReport(
  reportId: string,
  input: ReviewInput,
  accessToken: string,
): Promise<ReviewResult> {
  return apiFetch<ReviewResult>(`/reports/${reportId}/review`, accessToken, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
