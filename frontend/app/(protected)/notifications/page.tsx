"use client";

import React, { useCallback, useEffect, useState } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useNotificationStore } from "@/store/notification.store";
import type { Notification, NotificationChannel } from "@/types/notification";

// ---------------------------------------------------------------------------
// Priority styling helpers
// ---------------------------------------------------------------------------

const PRIORITY_STYLES: Record<
  string,
  { dot: string; label: string; badge: string }
> = {
  low: {
    dot: "bg-slate-400",
    label: "Low",
    badge: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  },
  medium: {
    dot: "bg-blue-500",
    label: "Medium",
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  },
  high: {
    dot: "bg-amber-500",
    label: "High",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  },
  critical: {
    dot: "bg-rose-500",
    label: "Critical",
    badge: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
  },
};

const CHANNEL_STYLES: Record<string, { icon: React.ReactNode; label: string }> =
  {
    in_app: {
      label: "In-App",
      icon: (
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>
      ),
    },
    email: {
      label: "Email",
      icon: (
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
      ),
    },
    sms: {
      label: "SMS",
      icon: (
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
      ),
    },
  };

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------------------
// Notification Card
// ---------------------------------------------------------------------------

interface NotificationCardProps {
  notification: Notification;
  onMarkRead: (id: string) => void;
  onDelete: (id: string) => void;
}

const NotificationCard: React.FC<NotificationCardProps> = ({
  notification,
  onMarkRead,
  onDelete,
}) => {
  const priority = PRIORITY_STYLES[notification.priority] ?? PRIORITY_STYLES.medium;
  const channel = CHANNEL_STYLES[notification.channel] ?? CHANNEL_STYLES.in_app;

  return (
    <div
      className={`group relative flex gap-4 p-4 rounded-2xl border transition-all duration-200 ${
        notification.is_read
          ? "bg-white dark:bg-gray-900 border-gray-100 dark:border-gray-800"
          : "bg-blue-50/60 dark:bg-blue-950/20 border-blue-200/60 dark:border-blue-900/40 shadow-sm"
      }`}
    >
      {/* Unread indicator dot */}
      {!notification.is_read && (
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-blue-500 rounded-r-full" />
      )}

      {/* Priority dot */}
      <div className="flex-shrink-0 mt-1">
        <div
          className={`w-2.5 h-2.5 rounded-full ring-2 ring-white dark:ring-gray-900 ${priority.dot}`}
          title={`${priority.label} priority`}
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <h3
            className={`text-sm font-semibold leading-tight ${
              notification.is_read
                ? "text-gray-600 dark:text-gray-400"
                : "text-gray-900 dark:text-white"
            }`}
          >
            {notification.title}
          </h3>
          <span className="text-[11px] text-gray-400 dark:text-gray-500 whitespace-nowrap flex-shrink-0">
            {formatRelativeTime(notification.created_at)}
          </span>
        </div>

        <p
          className={`mt-1 text-sm leading-relaxed ${
            notification.is_read
              ? "text-gray-400 dark:text-gray-500"
              : "text-gray-600 dark:text-gray-300"
          }`}
        >
          {notification.message}
        </p>

        {/* Meta badges */}
        <div className="mt-2.5 flex items-center gap-2 flex-wrap">
          {/* Channel */}
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400">
            {channel.icon}
            {channel.label}
          </span>

          {/* Priority */}
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${priority.badge}`}
          >
            {priority.label}
          </span>

          {/* Read status */}
          {notification.is_read && (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-gray-400 dark:text-gray-600">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                  clipRule="evenodd"
                />
              </svg>
              Read
            </span>
          )}

          {/* Email sent_at */}
          {notification.channel === "email" && notification.sent_at && (
            <span className="text-[10px] text-emerald-600 dark:text-emerald-400">
              Delivered
            </span>
          )}
          {notification.channel === "email" && !notification.sent_at && (
            <span className="text-[10px] text-amber-600 dark:text-amber-400">
              Not delivered
            </span>
          )}
        </div>
      </div>

      {/* Actions — visible on hover */}
      <div className="flex-shrink-0 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        {!notification.is_read && (
          <button
            id={`mark-read-${notification.id}`}
            onClick={() => onMarkRead(notification.id)}
            title="Mark as read"
            className="p-1.5 rounded-lg text-blue-500 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </button>
        )}
        <button
          id={`delete-${notification.id}`}
          onClick={() => onDelete(notification.id)}
          title="Delete notification"
          className="p-1.5 rounded-lg text-gray-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-colors focus:outline-none focus:ring-2 focus:ring-rose-400"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
            />
          </svg>
        </button>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

type FilterTab = "all" | "unread" | "in_app" | "email" | "sms";

const FILTER_TABS: { id: FilterTab; label: string }[] = [
  { id: "all", label: "All" },
  { id: "unread", label: "Unread" },
  { id: "in_app", label: "In-App" },
  { id: "email", label: "Email" },
  { id: "sms", label: "SMS" },
];

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function NotificationsPage() {
  const {
    notifications,
    unreadCount,
    isLoading,
    totalItems,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
    deleteNotification,
  } = useNotificationStore();

  const [activeFilter, setActiveFilter] = useState<FilterTab>("all");
  const [skip, setSkip] = useState(0);
  const LIMIT = 20;

  const buildParams = useCallback(
    (filter: FilterTab, offset: number) => {
      const params: {
        skip: number;
        limit: number;
        unread_only?: boolean;
        channel?: NotificationChannel;
      } = { skip: offset, limit: LIMIT };

      if (filter === "unread") params.unread_only = true;
      else if (filter === "in_app") params.channel = "in_app";
      else if (filter === "email") params.channel = "email";
      else if (filter === "sms") params.channel = "sms";

      return params;
    },
    [],
  );

  useEffect(() => {
    fetchNotifications(buildParams(activeFilter, skip));
  }, [fetchNotifications, buildParams, activeFilter, skip]);

  const handleFilterChange = (filter: FilterTab) => {
    setActiveFilter(filter);
    setSkip(0);
  };

  const handleMarkRead = async (id: string) => {
    await markAsRead(id);
  };

  const handleDelete = async (id: string) => {
    await deleteNotification(id);
  };

  const handleMarkAllRead = async () => {
    await markAllAsRead();
  };

  const totalPages = Math.max(1, Math.ceil(totalItems / LIMIT));
  const currentPage = Math.floor(skip / LIMIT) + 1;

  return (
    <DashboardLayout>
      <div className="p-6 max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">
                Notifications
              </h1>
              <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                {unreadCount > 0 ? (
                  <>
                    <span className="font-semibold text-blue-600 dark:text-blue-400">
                      {unreadCount}
                    </span>{" "}
                    unread notification{unreadCount !== 1 ? "s" : ""}
                  </>
                ) : (
                  "You're all caught up"
                )}
              </p>
            </div>

            {unreadCount > 0 && (
              <button
                id="mark-all-read-btn"
                onClick={handleMarkAllRead}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 transition-colors shadow-sm"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"
                  />
                </svg>
                Mark all as read
              </button>
            )}
          </div>

          {/* Filter tabs */}
          <div className="mt-5 flex gap-1 bg-gray-100 dark:bg-gray-800/60 rounded-xl p-1 w-fit">
            {FILTER_TABS.map((tab) => (
              <button
                key={tab.id}
                id={`filter-${tab.id}`}
                onClick={() => handleFilterChange(tab.id)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  activeFilter === tab.id
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                }`}
              >
                {tab.label}
                {tab.id === "unread" && unreadCount > 0 && (
                  <span className="ml-1.5 px-1.5 py-0.5 bg-rose-500 text-white text-[9px] rounded-full font-bold leading-none">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        {isLoading ? (
          <div className="flex justify-center py-20">
            <LoadingSpinner />
          </div>
        ) : notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-16 h-16 mb-4 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
              <svg
                className="w-8 h-8 text-gray-400 dark:text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300">
              {activeFilter === "unread"
                ? "No unread notifications"
                : "No notifications yet"}
            </h3>
            <p className="mt-1 text-sm text-gray-400 dark:text-gray-500">
              {activeFilter === "unread"
                ? "You're all caught up!"
                : "New notifications will appear here."}
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              {notifications.map((n: Notification) => (
                <NotificationCard
                  key={n.id}
                  notification={n}
                  onMarkRead={handleMarkRead}
                  onDelete={handleDelete}
                />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-6 flex items-center justify-between">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Showing {skip + 1}–{Math.min(skip + LIMIT, totalItems)} of{" "}
                  {totalItems}
                </p>
                <div className="flex gap-2">
                  <button
                    id="pagination-prev"
                    onClick={() => setSkip(Math.max(0, skip - LIMIT))}
                    disabled={currentPage === 1}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  >
                    Previous
                  </button>
                  <span className="px-3 py-1.5 text-xs font-medium text-gray-500">
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    id="pagination-next"
                    onClick={() => setSkip(skip + LIMIT)}
                    disabled={currentPage >= totalPages}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
