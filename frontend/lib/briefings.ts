import { apiFetch, publicApiFetch } from "./api";
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

export type PublicQuizQuestion = {
  id: string;
  position: number;
  question: LocaleText;
  explanation: LocaleText;
  options: LocaleText[];
};

export type PublicBriefing = {
  id: string;
  version: number;
  body: LocaleText;
  target_activity: string | null;
  target_location: string | null;
  valid_from: string;
  valid_to: string;
  approved_at: string;
  quiz_questions: PublicQuizQuestion[];
};

export type QuizAnswerResult = {
  response_id: string;
  is_correct: boolean;
  correct_option: number;
};

export type QuizProgress = {
  answers: Array<QuizAnswerResult & {
    question_id: string;
    selected_option: number;
  }>;
  answered_count: number;
  question_count: number;
  quiz_completed: boolean;
};

export type LearningBriefing = Omit<PublicBriefing, "quiz_questions"> & {
  qr_token: string;
  target_match: boolean;
  question_count: number;
  answered_count: number;
  quiz_answered: boolean;
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

export function getPublicBriefing(token: string): Promise<PublicBriefing> {
  return publicApiFetch<PublicBriefing>(`/briefings/${encodeURIComponent(token)}`);
}

export function submitQuizAnswer(
  token: string,
  questionId: string,
  selectedOption: number,
  accessToken?: string,
): Promise<QuizAnswerResult> {
  return publicApiFetch<QuizAnswerResult>(
    `/briefings/${encodeURIComponent(token)}/quiz`,
    {
      method: "POST",
      body: JSON.stringify({ question_id: questionId, selected_option: selectedOption }),
    },
    accessToken,
  );
}

export function getQuizProgress(
  token: string,
  accessToken: string,
): Promise<QuizProgress> {
  return apiFetch<QuizProgress>(
    `/briefings/${encodeURIComponent(token)}/progress`,
    accessToken,
  );
}

export function listLearningBriefings(accessToken: string): Promise<LearningBriefing[]> {
  return apiFetch<LearningBriefing[]>("/briefings", accessToken);
}
