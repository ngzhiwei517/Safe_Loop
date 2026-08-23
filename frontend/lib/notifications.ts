import { apiFetch } from "./api";

export const notificationKinds = [
  "assigned",
  "sent_back",
  "overdue",
  "info_requested",
  "alert_raised",
  "briefing_published",
  "report_closed",
] as const;

export type NotificationKind = (typeof notificationKinds)[number];

export type NotificationItem = {
  id: string;
  recipient_id: string;
  kind: NotificationKind;
  entity_type: string;
  entity_id: string;
  payload: Record<string, string | number | null>;
  read_at: string | null;
  delivery_date: string | null;
  created_at: string;
};

export type NotificationFeed = {
  items: NotificationItem[];
  unread_count: number;
  priority_unread_count: number;
  unresolved_sent_back_count: number;
};

export function listNotifications(
  accessToken: string,
  limit = 50,
): Promise<NotificationFeed> {
  return apiFetch<NotificationFeed>(`/notifications?limit=${limit}`, accessToken);
}

export function markNotificationRead(
  notificationId: string,
  accessToken: string,
): Promise<NotificationItem> {
  return apiFetch<NotificationItem>(`/notifications/${notificationId}/read`, accessToken, {
    method: "POST",
  });
}
