import { apiFetch } from "./api";

export type AlertItem = {
  id: string;
  report_id: string;
  human_ref: string;
  description_original: string;
  raised_by: string;
  raised_at: string;
  location_text: string | null;
  acknowledged_by: string | null;
  acknowledged_by_name: string | null;
  acknowledged_at: string | null;
  escalated_at: string | null;
  resolution_note: string | null;
};

export type ReporterAlertCopyKey =
  | "alert.reporter.sent"
  | "alert.reporter.escalated"
  | "alert.reporter.acknowledged";

export function reporterAlertCopyKey(alert: AlertItem): ReporterAlertCopyKey {
  if (alert.acknowledged_at && alert.acknowledged_by_name) {
    return "alert.reporter.acknowledged";
  }
  if (alert.escalated_at) return "alert.reporter.escalated";
  return "alert.reporter.sent";
}

export function raiseAlert(
  reportId: string,
  locationText: string,
  accessToken: string,
): Promise<AlertItem> {
  return apiFetch<AlertItem>("/alerts", accessToken, {
    method: "POST",
    body: JSON.stringify({
      report_id: reportId,
      location_text: locationText.trim() || null,
    }),
  });
}

export function getAlert(alertId: string, accessToken: string): Promise<AlertItem> {
  return apiFetch<AlertItem>(`/alerts/${alertId}`, accessToken);
}

export function listAlerts(accessToken: string): Promise<AlertItem[]> {
  return apiFetch<AlertItem[]>("/alerts", accessToken);
}

export function acknowledgeAlert(alertId: string, accessToken: string): Promise<AlertItem> {
  return apiFetch<AlertItem>(`/alerts/${alertId}/acknowledge`, accessToken, {
    method: "POST",
  });
}

export function resolveAlert(
  alertId: string,
  resolutionNote: string,
  accessToken: string,
): Promise<AlertItem> {
  return apiFetch<AlertItem>(`/alerts/${alertId}/resolve`, accessToken, {
    method: "POST",
    body: JSON.stringify({ resolution_note: resolutionNote }),
  });
}
