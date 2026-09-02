/**
 * Zustand notification store — Phase 10.
 *
 * Manages:
 *   - notifications: the current page of notifications
 *   - unreadCount:   the live unread count (polled every 30 seconds)
 *   - isLoading:     fetch-in-progress flag
 *
 * Polling design:
 *   - A single module-level interval ID ensures only ONE polling loop
 *     exists per browser session regardless of how many components mount.
 *   - startPolling() is idempotent — calling it multiple times has no effect.
 *   - stopPolling()  clears the interval; called by clearAuth() on logout.
 *   - The interval only polls GET /notifications/count (cheap query).
 *   - Full list is loaded on-demand when the user opens the Notification Center.
 *
 * Optimistic updates:
 *   - markAsRead / deleteNotification mutate local state immediately,
 *     then reconcile with the server response.
 *   - On failure the store re-fetches the count to restore accuracy.
 *
 * Security:
 *   - The store never stores SMTP credentials or other sensitive data.
 *   - Notification content is stored as plain text (rendered as text in the UI).
 */

"use client";

import { create } from "zustand";
import * as notificationService from "@/services/notification.service";
import type { Notification, NotificationListParams } from "@/types/notification";

// ---------------------------------------------------------------------------
// Polling — singleton interval (module-level, survives component remounts)
// ---------------------------------------------------------------------------

let _pollIntervalId: ReturnType<typeof setInterval> | null = null;
const POLL_INTERVAL_MS = 30_000; // 30 seconds

// ---------------------------------------------------------------------------
// Store interface
// ---------------------------------------------------------------------------

interface NotificationState {
  /** Current page of notifications (populated when the user opens the center). */
  notifications: Notification[];

  /** Live unread notification count — updated by polling. */
  unreadCount: number;

  /** True while a fetchNotifications() call is in-flight. */
  isLoading: boolean;

  /** Total items on the backend (for pagination). */
  totalItems: number;

  /**
   * Load the notification list for the current user.
   * Populates `notifications`, `unreadCount`, and `totalItems`.
   */
  fetchNotifications: (params?: NotificationListParams) => Promise<void>;

  /**
   * Silently refresh the unread count without touching the list.
   * Called by the polling interval.
   */
  refreshUnreadCount: () => Promise<void>;

  /**
   * Start the 30-second polling loop for unread count.
   * Idempotent — safe to call from multiple components.
   */
  startPolling: () => void;

  /**
   * Stop the polling loop.
   * Must be called on logout to prevent stale polling.
   */
  stopPolling: () => void;

  /**
   * Mark a single notification as read.
   * Applies an optimistic update then reconciles with the server response.
   */
  markAsRead: (id: string) => Promise<void>;

  /**
   * Mark all notifications as read.
   * Updates both the list and the unread count.
   */
  markAllAsRead: () => Promise<void>;

  /**
   * Delete a notification.
   * Removes it from the local list optimistically, then confirms deletion.
   */
  deleteNotification: (id: string) => Promise<void>;

  /** Reset store to initial state (called on logout). */
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  isLoading: false,
  totalItems: 0,

  // -------------------------------------------------------------------------
  // fetchNotifications
  // -------------------------------------------------------------------------
  fetchNotifications: async (params?: NotificationListParams) => {
    set({ isLoading: true });
    try {
      const res = await notificationService.fetchNotifications(params);
      set({
        notifications: res.data,
        unreadCount: res.unread_count,
        totalItems: res.meta.total_items,
        isLoading: false,
      });
    } catch {
      set({ isLoading: false });
    }
  },

  // -------------------------------------------------------------------------
  // refreshUnreadCount  (cheap polling call)
  // -------------------------------------------------------------------------
  refreshUnreadCount: async () => {
    try {
      const res = await notificationService.getUnreadCount();
      set({ unreadCount: res.data.unread_count });
    } catch {
      // Non-critical — silently ignore network errors during polling
    }
  },

  // -------------------------------------------------------------------------
  // startPolling  (idempotent)
  // -------------------------------------------------------------------------
  startPolling: () => {
    if (_pollIntervalId !== null) return; // Already polling

    // Fetch immediately on start, then every 30 s
    get().refreshUnreadCount();

    _pollIntervalId = setInterval(() => {
      get().refreshUnreadCount();
    }, POLL_INTERVAL_MS);
  },

  // -------------------------------------------------------------------------
  // stopPolling
  // -------------------------------------------------------------------------
  stopPolling: () => {
    if (_pollIntervalId !== null) {
      clearInterval(_pollIntervalId);
      _pollIntervalId = null;
    }
  },

  // -------------------------------------------------------------------------
  // markAsRead  (optimistic)
  // -------------------------------------------------------------------------
  markAsRead: async (id: string) => {
    // Optimistic update
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, is_read: true } : n,
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    }));

    try {
      const res = await notificationService.markAsRead(id);
      // Reconcile with server truth
      set((state) => ({
        notifications: state.notifications.map((n) =>
          n.id === id ? res.data : n,
        ),
      }));
    } catch {
      // Revert optimistic update by refreshing the count
      get().refreshUnreadCount();
      // Re-fetch the list to restore accurate state
      get().fetchNotifications();
    }
  },

  // -------------------------------------------------------------------------
  // markAllAsRead
  // -------------------------------------------------------------------------
  markAllAsRead: async () => {
    // Optimistic update
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, is_read: true })),
      unreadCount: 0,
    }));

    try {
      const res = await notificationService.markAllAsRead();
      set({ unreadCount: res.data.unread_count });
    } catch {
      // Revert by re-fetching
      get().refreshUnreadCount();
      get().fetchNotifications();
    }
  },

  // -------------------------------------------------------------------------
  // deleteNotification  (optimistic)
  // -------------------------------------------------------------------------
  deleteNotification: async (id: string) => {
    // Save the item before removing it for potential rollback
    const removed = get().notifications.find((n) => n.id === id);

    // Optimistic update
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
      unreadCount:
        removed && !removed.is_read
          ? Math.max(0, state.unreadCount - 1)
          : state.unreadCount,
      totalItems: Math.max(0, state.totalItems - 1),
    }));

    try {
      await notificationService.deleteNotification(id);
    } catch {
      // Rollback: restore the removed item and refresh count
      if (removed) {
        set((state) => ({
          notifications: [removed, ...state.notifications],
          totalItems: state.totalItems + 1,
        }));
      }
      get().refreshUnreadCount();
    }
  },

  // -------------------------------------------------------------------------
  // reset
  // -------------------------------------------------------------------------
  reset: () => {
    get().stopPolling();
    set({
      notifications: [],
      unreadCount: 0,
      isLoading: false,
      totalItems: 0,
    });
  },
}));
