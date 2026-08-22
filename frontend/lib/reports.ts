import { apiFetch } from "./api";
import type { Locale } from "./locales";
import { uploadReportPhoto, type MediaPhase, type ReportPhotoUpload } from "./media";
import { reportStatus, type ReportStatus } from "./stateMachine";

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

export type ReportDetail = {
  id: string;
  human_ref: string;
  status: ReportStatus;
  media: ReportMedia[];
  available_transitions: ReportStatus[];
};

export async function fileReport(
  input: NewReportInput,
  accessToken: string,
  photo?: ReportPhotoUpload,
): Promise<SubmittedReport> {
  const created = await apiFetch<CreatedReport>("/reports", accessToken, { method: "POST", body: JSON.stringify(input) });
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

export function getReport(reportId: string, accessToken: string): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/reports/${reportId}`, accessToken);
}
