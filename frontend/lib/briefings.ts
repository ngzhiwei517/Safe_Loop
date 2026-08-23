import { apiFetch } from "./api";
import type { Locale } from "./locales";

export type LocaleText = Record<Locale, string>;
export type BriefingStatus = "draft" | "published";

export type ManagedQuizQuestion = {
  id: string;
  position: number;
  question: LocaleText;
  explanation: LocaleText;
  options: LocaleText[];
  correct_option: number;
  created_at: string;
};

export type ManagedBriefing = {
  id: string;
  report_id: string;
  human_ref: string;
  report_status: string;
  version: number;
  body: LocaleText;
  status: BriefingStatus;
  target_activity: string | null;
  target_location: string | null;
  valid_from: string | null;
  valid_to: string | null;
  qr_token: string | null;
  approved_by: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  created_at: string;
  question_count?: number;
  quiz_questions?: ManagedQuizQuestion[];
  available_transitions: Array<{
    event: string;
    target: string;
    requires_reason: boolean;
  }>;
};

export type BriefingEditPayload = {
  body: LocaleText;
  target_activity: string | null;
  target_location: string | null;
  valid_from: string | null;
  valid_to: string | null;
  quiz_questions: Array<{
    position: number;
    question: LocaleText;
    explanation: LocaleText;
    options: LocaleText[];
    correct_option: number;
  }>;
};

export function listManagedBriefings(accessToken: string): Promise<ManagedBriefing[]> {
  return apiFetch<ManagedBriefing[]>("/briefings/manage", accessToken);
}

export function getManagedBriefing(
  briefingId: string,
  accessToken: string,
): Promise<ManagedBriefing> {
  return apiFetch<ManagedBriefing>(`/briefings/manage/${briefingId}`, accessToken);
}

export function saveManagedBriefing(
  briefingId: string,
  payload: BriefingEditPayload,
  accessToken: string,
): Promise<ManagedBriefing> {
  return apiFetch<ManagedBriefing>(`/briefings/manage/${briefingId}`, accessToken, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function publishManagedBriefing(
  briefingId: string,
  accessToken: string,
): Promise<ManagedBriefing> {
  return apiFetch<ManagedBriefing>(`/briefings/manage/${briefingId}/publish`, accessToken, {
    method: "POST",
  });
}
