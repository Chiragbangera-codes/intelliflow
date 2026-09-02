"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { AIChat } from "@/components/ai/AIChat";
import { useAuthStore } from "@/store/auth.store";
import { getDashboardStats } from "@/services/dashboard.service";
import type { DashboardStats } from "@/types";

// Formats a number with locale separators
function fmtNum(n: number | undefined | null) {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString();
}

export default function DashboardPage() {
  const { user } = useAuthStore();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStats() {
      try {
        setLoading(true);
        const res = await getDashboardStats();
        if (res.success) setStats(res.data);
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : "Failed to load dashboard stats";
        setError(errorMsg);
      } finally {
        setLoading(false);
      }
    }
    loadStats();
  }, []);

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1200 }}>

        {/* ── Hero heading ── */}
        <div style={{ marginBottom: 48 }}>
          <p
            className="eyebrow"
            style={{ marginBottom: 14, color: "var(--accent)" }}
          >
            Document Intelligence
          </p>
          <h1
            style={{
              fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
              fontSize: "clamp(2rem, 3vw, 2.75rem)",
              fontWeight: 800,
              letterSpacing: "-0.04em",
              color: "#f8fafc",
              lineHeight: 1.1,
              margin: 0,
            }}
          >
            {user
              ? <>Good to have you back,<br /><span style={{ color: "var(--ink-40)" }}>{user.first_name}.</span></>
              : "Everything your organization knows."}
          </h1>
        </div>

        {/* ── Metric Strip ── */}
        {loading ? (
          <div style={{ marginBottom: 48 }}>
            <LoadingSpinner message="Loading workspace data..." />
          </div>
        ) : error ? (
          <div
            style={{
              padding: "14px 18px",
              background: "rgb(220 38 38 / 0.08)",
              border: "1px solid rgb(220 38 38 / 0.2)",
              borderRadius: 8,
              fontSize: 13,
              color: "#f87171",
              marginBottom: 40,
            }}
          >
            {error}
          </div>
        ) : (
          <div className="metric-strip" style={{ marginBottom: 48 }}>
            <div className="metric-strip-item">
              <span className="metric-strip-value">{fmtNum(stats?.total_documents)}</span>
              <span className="metric-strip-label">Documents</span>
            </div>
            <div className="metric-strip-item">
              <span className="metric-strip-value">{fmtNum(stats?.total_workflows)}</span>
              <span className="metric-strip-label">Workflows</span>
            </div>
            <div className="metric-strip-item">
              <span className="metric-strip-value">{fmtNum(stats?.pending_executions)}</span>
              <span className="metric-strip-label">Pending</span>
            </div>
            <div className="metric-strip-item">
              <span className="metric-strip-value">{fmtNum(stats?.total_departments)}</span>
              <span className="metric-strip-label">Departments</span>
            </div>
            <div className="metric-strip-item">
              <span className="metric-strip-value">{fmtNum(stats?.total_employees)}</span>
              <span className="metric-strip-label">People</span>
            </div>
          </div>
        )}

        {/* ── Main two-column ── */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 340px",
            gap: 40,
            marginBottom: 48,
            alignItems: "start",
          }}
        >
          {/* Left — AI workspace */}
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 20,
              }}
            >
              <div>
                <p className="eyebrow" style={{ marginBottom: 6 }}>AI Assistant</p>
                <h2
                  style={{
                    fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
                    fontSize: 20,
                    fontWeight: 700,
                    letterSpacing: "-0.025em",
                    color: "#f1f5f9",
                    margin: 0,
                  }}
                >
                  Ask your document library
                </h2>
              </div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                  color: "#4ade80",
                  background: "rgb(22 163 74 / 0.1)",
                  border: "1px solid rgb(22 163 74 / 0.2)",
                  borderRadius: 4,
                  padding: "3px 8px",
                }}
              >
                ● Live
              </span>
            </div>
            <div
              style={{
                background: "var(--ink-80)",
                border: "1px solid var(--ink-70)",
                borderRadius: 12,
                overflow: "hidden",
              }}
            >
              <AIChat defaultTopK={5} />
            </div>
          </div>

          {/* Right — Quick navigation (editorial, not cards) */}
          <div>
            <p className="eyebrow" style={{ marginBottom: 20 }}>Navigate</p>

            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {[
                {
                  href: "/documents",
                  label: "Documents",
                  sub: "Library & versions",
                  tag: fmtNum(stats?.total_documents),
                },
                {
                  href: "/workflows",
                  label: "Workflows",
                  sub: "Automation pipelines",
                  tag: fmtNum(stats?.total_workflows),
                },
                {
                  href: "/analytics",
                  label: "Analytics",
                  sub: "Operational insights",
                  tag: null,
                  roles: ["admin", "manager", "hr", "finance"],
                },
                {
                  href: "/predictions",
                  label: "Predictions",
                  sub: "AI forecasts",
                  tag: null,
                  roles: ["admin", "manager", "hr", "finance"],
                },
                {
                  href: "/departments",
                  label: "Departments",
                  sub: "Organizational units",
                  tag: fmtNum(stats?.total_departments),
                },
                {
                  href: "/employees",
                  label: "People",
                  sub: "Employee directory",
                  tag: fmtNum(stats?.total_employees),
                },
              ]
                .filter((item) => {
                  if (!item.roles) return true;
                  if (!user?.role) return false;
                  return item.roles.includes(user.role.toLowerCase());
                })
                .map((item, i, arr) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "14px 0",
                      borderBottom: i < arr.length - 1 ? "1px solid var(--ink-70)" : "none",
                      textDecoration: "none",
                      transition: "color 0.1s",
                    }}
                    onMouseEnter={(e) => {
                      const title = e.currentTarget.querySelector(".nav-link-title") as HTMLElement;
                      if (title) title.style.color = "#f1f5f9";
                    }}
                    onMouseLeave={(e) => {
                      const title = e.currentTarget.querySelector(".nav-link-title") as HTMLElement;
                      if (title) title.style.color = "#94a3b8";
                    }}
                  >
                    <div>
                      <p
                        className="nav-link-title"
                        style={{
                          fontSize: 14,
                          fontWeight: 600,
                          color: "#94a3b8",
                          margin: 0,
                          transition: "color 0.1s",
                          letterSpacing: "-0.01em",
                        }}
                      >
                        {item.label}
                      </p>
                      <p style={{ fontSize: 11, color: "var(--ink-60)", margin: 0 }}>
                        {item.sub}
                      </p>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {item.tag && item.tag !== "—" && (
                        <span style={{ fontSize: 12, color: "var(--ink-40)", fontWeight: 600 }}>
                          {item.tag}
                        </span>
                      )}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ink-60)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="9 18 15 12 9 6" />
                      </svg>
                    </div>
                  </Link>
                ))}
            </div>
          </div>
        </div>

        {/* ── Document workspace links — editorial horizontal section ── */}
        <div
          style={{
            borderTop: "1px solid var(--ink-70)",
            paddingTop: 40,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: 24,
            }}
          >
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Quick Actions</p>
              <h2
                style={{
                  fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
                  fontSize: 20,
                  fontWeight: 700,
                  letterSpacing: "-0.025em",
                  color: "#f1f5f9",
                  margin: 0,
                }}
              >
                Document operations
              </h2>
            </div>
            <Link
              href="/documents"
              style={{ fontSize: 13, fontWeight: 600, color: "var(--accent)", textDecoration: "none" }}
            >
              View all documents →
            </Link>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1 }}>
            {[
              {
                href: "/documents",
                action: "Upload document",
                desc: "Add files to your document library with automatic processing.",
                tag: "Documents",
              },
              {
                href: "/workflows",
                action: "Create workflow",
                desc: "Design an approval pipeline or automation for your team.",
                tag: "Workflows",
              },
              {
                href: "/reports",
                action: "Generate report",
                desc: "Export analytical data as PDF, CSV or Excel.",
                tag: "Reports",
              },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                style={{
                  display: "block",
                  padding: "24px 28px",
                  background: "var(--ink-80)",
                  border: "1px solid var(--ink-70)",
                  borderRadius: 0,
                  textDecoration: "none",
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "rgb(255 255 255 / 0.03)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "var(--ink-80)";
                }}
              >
                <p className="eyebrow" style={{ marginBottom: 10 }}>{item.tag}</p>
                <p
                  style={{
                    fontSize: 15,
                    fontWeight: 700,
                    color: "#f1f5f9",
                    marginBottom: 6,
                    letterSpacing: "-0.015em",
                  }}
                >
                  {item.action}
                </p>
                <p style={{ fontSize: 13, color: "var(--ink-40)", lineHeight: 1.5 }}>
                  {item.desc}
                </p>
              </Link>
            ))}
          </div>
        </div>

      </div>
    </DashboardLayout>
  );
}
