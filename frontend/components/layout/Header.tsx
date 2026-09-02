"use client";

import React from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth.store";
import { useNotificationStore } from "@/store/notification.store";

interface HeaderProps {
  title?: string;
  description?: string;
}

const ROLE_COLORS: Record<string, string> = {
  admin: "badge-admin",
  hr: "badge-hr",
  manager: "badge-manager",
  finance: "badge-finance",
  employee: "badge-employee",
};

export const Header: React.FC<HeaderProps> = () => {
  const router = useRouter();
  const pathname = usePathname();
  const { user, clearAuth } = useAuthStore();
  const unreadCount = useNotificationStore((s) => s.unreadCount);

  const handleLogout = () => {
    clearAuth();
    router.push("/login");
  };

  // Derive page title from pathname for breadcrumb
  const getPageLabel = () => {
    const segments = pathname.replace(/^\//, "").split("/");
    if (segments.length === 0 || !segments[0]) return "IntelliFlow";
    return segments
      .map((s) => s.charAt(0).toUpperCase() + s.slice(1).replace(/-/g, " "))
      .join(" / ");
  };

  return (
    <header
      style={{
        height: "var(--header-h)",
        background: "var(--ink-90)",
        borderBottom: "1px solid var(--ink-70)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 28px",
        position: "sticky",
        top: 0,
        zIndex: 20,
        flexShrink: 0,
      }}
    >
      {/* Left: breadcrumb label */}
      <span
        style={{
          fontSize: 13,
          fontWeight: 500,
          color: "var(--ink-40)",
          letterSpacing: "0.01em",
        }}
      >
        {getPageLabel()}
      </span>

      {/* Right: actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {user && (
          <>
            {/* Role badge */}
            <span
              className={`badge ${ROLE_COLORS[user.role] || "badge-employee"}`}
            >
              {user.role}
            </span>

            {/* Notification bell */}
            <button
              id="notification-bell"
              onClick={() => router.push("/notifications")}
              aria-label={
                unreadCount > 0
                  ? `${unreadCount} unread notifications`
                  : "Notifications"
              }
              style={{
                position: "relative",
                width: 32,
                height: 32,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "transparent",
                border: "none",
                borderRadius: 6,
                color: "var(--ink-40)",
                cursor: "pointer",
                transition: "background 0.1s, color 0.1s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--ink-80)";
                e.currentTarget.style.color = "#e2e8f0";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--ink-40)";
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" />
              </svg>
              {unreadCount > 0 && (
                <span
                  id="notification-badge"
                  aria-hidden="true"
                  style={{
                    position: "absolute",
                    top: 3,
                    right: 3,
                    width: 8,
                    height: 8,
                    background: "#ef4444",
                    borderRadius: "50%",
                    border: "2px solid var(--ink-90)",
                  }}
                />
              )}
            </button>

            {/* User name */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                borderLeft: "1px solid var(--ink-70)",
                paddingLeft: 12,
                marginLeft: 4,
              }}
            >
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: "#94a3b8",
                }}
              >
                {user.first_name} {user.last_name}
              </span>

              <button
                onClick={handleLogout}
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--ink-40)",
                  background: "transparent",
                  border: "1px solid var(--ink-70)",
                  borderRadius: 5,
                  padding: "4px 10px",
                  cursor: "pointer",
                  letterSpacing: "0.01em",
                  transition: "all 0.1s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--ink-80)";
                  e.currentTarget.style.color = "#e2e8f0";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = "var(--ink-40)";
                }}
              >
                Sign out
              </button>
            </div>
          </>
        )}
      </div>
    </header>
  );
};
