/**
 * Notification types — Phase 10.
 *
 * Mirrors the backend Notification ORM model and API schemas exactly.
 * Enum values must match the backend NotificationChannel / NotificationPriority enums.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type NotificationChannel = "in_app" | "email" | "sms";

export type NotificationPriority = "low" | "medium" | "high" | "critical";

// ---------------------------------------------------------------------------
// Core entity
// ---------------------------------------------------------------------------

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  message: string;
  channel: NotificationChannel;
  is_read: boolean;
  priority: NotificationPriority;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Request types
// ---------------------------------------------------------------------------

export interface NotificationCreateRequest {
  user_id: string;
  title: string;
  message: string;
  channel?: NotificationChannel;
  priority?: NotificationPriority;
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface NotificationCountResponse {
  unread_count: number;
}

export interface NotificationMarkAllReadResponse {
  updated: number;
  unread_count: number;
}

export interface NotificationListMeta {
  skip: number;
  limit: number;
  total_items: number;
  total_pages: number;
  page: number;
}

// ---------------------------------------------------------------------------
// Filter params
// ---------------------------------------------------------------------------

export interface NotificationListParams {
  skip?: number;
  limit?: number;
  unread_only?: boolean;
  channel?: NotificationChannel;
}
