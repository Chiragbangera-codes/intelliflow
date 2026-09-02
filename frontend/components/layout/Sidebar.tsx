"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth.store";
import { useNotificationStore } from "@/store/notification.store";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  roles?: string[];
  badge?: number;
}

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const { user } = useAuthStore();
  const unreadCount = useNotificationStore((s) => s.unreadCount);

  const navItems: NavItem[] = [
    {
      label: "Dashboard",
      href: "/dashboard",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
      ),
    },
    {
      label: "Documents",
      href: "/documents",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="9" y1="13" x2="15" y2="13" />
          <line x1="9" y1="17" x2="13" y2="17" />
        </svg>
      ),
    },
    {
      label: "Workflows",
      href: "/workflows",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="5" r="2" />
          <circle cx="5" cy="19" r="2" />
          <circle cx="19" cy="19" r="2" />
          <path d="M12 7v4M5 17l7-6M19 17l-7-6" />
        </svg>
      ),
    },
    {
      label: "Analytics",
      href: "/analytics",
      roles: ["admin", "manager", "hr", "finance"],
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="20" x2="18" y2="10" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="6" y1="20" x2="6" y2="14" />
        </svg>
      ),
    },
    {
      label: "Predictions",
      href: "/predictions",
      roles: ["admin", "manager", "hr", "finance"],
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </svg>
      ),
    },
    {
      label: "Reports",
      href: "/reports",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 17v-2m3 2v-4m3 4v-6M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
      ),
    },
    {
      label: "Departments",
      href: "/departments",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
      ),
    },
    {
      label: "Employees",
      href: "/employees",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
        </svg>
      ),
    },
    {
      label: "Notifications",
      href: "/notifications",
      badge: unreadCount,
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" />
        </svg>
      ),
    },
  ];

  const visibleNavItems = navItems.filter((item) => {
    if (!item.roles || item.roles.length === 0) return true;
    if (!user?.role) return false;
    return item.roles.includes(user.role.toLowerCase());
  });

  const isActive = (href: string) =>
    pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`));

  return (
    <aside
      style={{
        width: "var(--sidebar-w)",
        minWidth: "var(--sidebar-w)",
        background: "var(--ink)",
        borderRight: "1px solid var(--ink-70)",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        minHeight: "100vh",
      }}
    >
      {/* Brand */}
      <div
        style={{
          height: "var(--header-h)",
          borderBottom: "1px solid var(--ink-70)",
          display: "flex",
          alignItems: "center",
          padding: "0 16px",
          gap: "10px",
          flexShrink: 0,
        }}
      >
        {/* Logo mark — document icon */}
        <div
          style={{
            width: 28,
            height: 28,
            background: "var(--accent)",
            borderRadius: 6,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <div>
          <span
            style={{
              display: "block",
              fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
              fontWeight: 700,
              fontSize: 13,
              letterSpacing: "-0.02em",
              color: "#f1f5f9",
              lineHeight: 1.2,
            }}
          >
            IntelliFlow
          </span>
          <span
            style={{
              display: "block",
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--ink-40)",
              lineHeight: 1,
              marginTop: 2,
            }}
          >
            Document AI
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: "20px 10px", overflowY: "auto" }}>
        {/* Main nav */}
        <div style={{ marginBottom: 24 }}>
          <p style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--ink-60)",
            padding: "0 10px",
            marginBottom: 6,
          }}>
            Workspace
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {visibleNavItems.slice(0, 5).map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="nav-item"
                  style={{
                    color: active ? "#f1f5f9" : "var(--ink-40)",
                    background: active ? "rgb(255 255 255 / 0.06)" : "transparent",
                    borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                    borderRadius: "0 6px 6px 0",
                    paddingLeft: active ? "10px" : "12px",
                    fontWeight: active ? 600 : 500,
                    fontSize: 14,
                  }}
                >
                  <span style={{ color: active ? "#93c5fd" : "var(--ink-60)", flexShrink: 0 }}>
                    {item.icon}
                  </span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {item.badge && item.badge > 0 ? (
                    <span
                      style={{
                        background: "#ef4444",
                        color: "white",
                        fontSize: 10,
                        fontWeight: 700,
                        minWidth: 18,
                        height: 18,
                        borderRadius: 9,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: "0 5px",
                      }}
                    >
                      {item.badge > 99 ? "99+" : item.badge}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </div>
        </div>

        {/* Secondary nav */}
        <div style={{ marginBottom: 24 }}>
          <p style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--ink-60)",
            padding: "0 10px",
            marginBottom: 6,
          }}>
            People & Docs
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {visibleNavItems.slice(5).map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="nav-item"
                  style={{
                    color: active ? "#f1f5f9" : "var(--ink-40)",
                    background: active ? "rgb(255 255 255 / 0.06)" : "transparent",
                    borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                    borderRadius: "0 6px 6px 0",
                    paddingLeft: active ? "10px" : "12px",
                    fontWeight: active ? 600 : 500,
                    fontSize: 14,
                  }}
                >
                  <span style={{ color: active ? "#93c5fd" : "var(--ink-60)", flexShrink: 0 }}>
                    {item.icon}
                  </span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {item.badge && item.badge > 0 ? (
                    <span
                      style={{
                        background: "#ef4444",
                        color: "white",
                        fontSize: 10,
                        fontWeight: 700,
                        minWidth: 18,
                        height: 18,
                        borderRadius: 9,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: "0 5px",
                      }}
                    >
                      {item.badge > 99 ? "99+" : item.badge}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </div>
        </div>

        {/* Admin Section */}
        {user?.role === "admin" && (
          <div>
            <p style={{
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--ink-60)",
              padding: "0 10px",
              marginBottom: 6,
            }}>
              Administration
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { href: "/admin/security", label: "Security & Audit" },
                { href: "/admin/system", label: "System Health" },
                { href: "/admin/integrations", label: "Integrations" },
                { href: "/admin/webhooks", label: "Webhooks" },
                { href: "/admin/automations", label: "Automations" },
                { href: "/admin/events", label: "Event Activity" },
              ].map((item) => {
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="nav-item"
                    style={{
                      color: active ? "#f1f5f9" : "var(--ink-40)",
                      background: active ? "rgb(255 255 255 / 0.06)" : "transparent",
                      borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                      borderRadius: "0 6px 6px 0",
                      paddingLeft: active ? "10px" : "12px",
                      fontWeight: active ? 600 : 500,
                      fontSize: 13,
                    }}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </nav>

      {/* User Profile Footer */}
      {user && (
        <div
          style={{
            borderTop: "1px solid var(--ink-70)",
            padding: "14px 14px",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          {/* Avatar */}
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 6,
              background: "var(--ink-80)",
              border: "1px solid var(--ink-70)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 11,
              fontWeight: 700,
              color: "#94a3b8",
              flexShrink: 0,
              letterSpacing: "0.02em",
            }}
          >
            {user.first_name?.[0]}
            {user.last_name?.[0]}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#cbd5e1",
              margin: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              lineHeight: 1.3,
            }}>
              {user.first_name} {user.last_name}
            </p>
            <p style={{
              fontSize: 10,
              color: "var(--ink-40)",
              margin: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              lineHeight: 1.3,
              textTransform: "capitalize",
            }}>
              {user.role}
            </p>
          </div>
        </div>
      )}
    </aside>
  );
};
