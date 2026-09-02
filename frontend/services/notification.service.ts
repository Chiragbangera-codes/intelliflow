/**
 * Notification API service — Phase 10.
 *
 * Wraps all 7 /api/v1/notifications endpoints.
 * Uses the shared apiClient (with JWT interceptor) — no second client.
 *
 * All functions are pure async — side effects (state updates) live in the store.
 */

import apiClient from "./api";
import type { ApiResponse } from "@/types";
import type {
  Notification,
  NotificationCountResponse,
  NotificationCreateRequest,
  NotificationListMeta,
  NotificationListParams,
  NotificationMarkAllReadResponse,
} from "@/types/notification";

const BASE = "/notifications";

// ---------------------------------------------------------------------------
// List notifications
// ---------------------------------------------------------------------------

export async function fetchNotifications(params?: NotificationListParams): Promise<{
  success: boolean;
  message: string;
  data: Notification[];
  meta: NotificationListMeta;
  unread_count: number;
}> {
  const res = await apiClient.get(BASE, { params });
  return res.data;
}

// ---------------------------------------------------------------------------
// Get unread count
// ---------------------------------------------------------------------------

export async function getUnreadCount(): Promise<ApiResponse<NotificationCountResponse>> {
  const res = await apiClient.get<ApiResponse<NotificationCountResponse>>(
    `${BASE}/count`,
  );
  return res.data;
}

// ---------------------------------------------------------------------------
// Get single notification
// ---------------------------------------------------------------------------

export async function getNotification(id: string): Promise<ApiResponse<Notification>> {
  const res = await apiClient.get<ApiResponse<Notification>>(`${BASE}/${id}`);
  return res.data;
}

// ---------------------------------------------------------------------------
// Mark single notification as read
// ---------------------------------------------------------------------------

export async function markAsRead(id: string): Promise<ApiResponse<Notification>> {
  const res = await apiClient.patch<ApiResponse<Notification>>(
    `${BASE}/${id}/read`,
  );
  return res.data;
}

// ---------------------------------------------------------------------------
// Mark all notifications as read
// ---------------------------------------------------------------------------

export async function markAllAsRead(): Promise<
  ApiResponse<NotificationMarkAllReadResponse>
> {
  const res = await apiClient.patch<ApiResponse<NotificationMarkAllReadResponse>>(
    `${BASE}/read-all`,
  );
  return res.data;
}

// ---------------------------------------------------------------------------
// Create notification (Admin / Manager only)
// ---------------------------------------------------------------------------

export async function createNotification(
  payload: NotificationCreateRequest,
): Promise<ApiResponse<Notification>> {
  const res = await apiClient.post<ApiResponse<Notification>>(BASE, payload);
  return res.data;
}

// ---------------------------------------------------------------------------
// Delete notification
// ---------------------------------------------------------------------------

export async function deleteNotification(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}
