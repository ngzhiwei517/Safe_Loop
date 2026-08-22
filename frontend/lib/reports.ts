import { apiFetch } from "./api";
import type { Locale } from "./locales";
import { reportStatus } from "./stateMachine";

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

export async function fileReport(input: NewReportInput, accessToken: string): Promise<SubmittedReport> {
  const created = await apiFetch<CreatedReport>("/reports", accessToken, { method: "POST", body: JSON.stringify(input) });
  return apiFetch<SubmittedReport>(`/reports/${created.id}/transition`, accessToken, {
    method: "POST",
    body: JSON.stringify({ target: reportStatus.submitted }),
  });
}
