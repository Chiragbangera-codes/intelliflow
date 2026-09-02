"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth.store";
import { useNotificationStore } from "@/store/notification.store";
import { Badge } from "@/components/ui/Badge";

interface HeaderProps {
  title?: string;
  description?: string;
}

export const Header: React.FC<HeaderProps> = ({ title, description }) => {
  const router = useRouter();
  const { user, clearAuth } = useAuthStore();
  const unreadCount = useNotificationStore((s) => s.unreadCount);

  const handleLogout = () => {
    clearAuth();
    router.push("/login");
  };

  const handleBellClick = () => {
    router.push("/notifications");
  };

  const getRoleVariant = (role?: string) => {
    switch (role) {
      case "admin":
        return "primary";
      case "hr":
        return "info";
      case "manager":
        return "warning";
      case "finance":
        return "success";
      default:
        return "neutral";
    }
  };

  return (
    <header className="h-16 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-8 flex items-center justify-between sticky top-0 z-10">
      <div>
        {title && (
          <h1 className="text-xl font-bold text-gray-900 dark:text-white tracking-tight">{title}</h1>
        )}
        {description && (
          <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <div className="flex items-center gap-3">
            <Badge variant={getRoleVariant(user.role)} size="sm">
              {user.role}
            </Badge>

            {/* Notification Bell */}
            <button
              id="notification-bell"
              onClick={handleBellClick}
              aria-label={
                unreadCount > 0
                  ? `${unreadCount} unread notification${unreadCount !== 1 ? "s" : ""}`
                  : "Notifications"
              }
              title="Notifications"
              className="relative p-2 rounded-xl text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-all focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {/* Bell icon */}
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.75}
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>

              {/* Unread badge — hidden at zero */}
              {unreadCount > 0 && (
                <span
                  id="notification-badge"
                  className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center bg-rose-500 text-white text-[10px] font-bold rounded-full leading-none shadow-sm animate-pulse"
                  aria-hidden="true"
                >
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </button>

            <div className="hidden sm:block text-right">
              <p className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">
                {user.first_name} {user.last_name}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{user.email}</p>
            </div>

            <button
              onClick={handleLogout}
              className="px-3 py-1.5 text-xs font-medium text-rose-600 hover:text-white hover:bg-rose-600 border border-rose-200 dark:border-rose-900/40 rounded-xl transition-all shadow-2xs"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
