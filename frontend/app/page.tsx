"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth.store";
import Link from "next/link";

export default function HomePage() {
  const router = useRouter();
  const { isAuthenticated, isInitializing, initialize } = useAuthStore();

  useEffect(() => {
    initialize();
  }, [initialize]);

  // If authenticated, redirect to dashboard automatically
  useEffect(() => {
    if (!isInitializing && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, isInitializing, router]);

  if (isInitializing) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--ink)",
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            border: "2px solid var(--ink-70)",
            borderTopColor: "var(--accent)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--ink)", color: "#e2e8f0" }}>

      {/* Navigation */}
      <nav
        style={{
          height: 64,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 48px",
          borderBottom: "1px solid var(--ink-70)",
          position: "sticky",
          top: 0,
          background: "var(--ink)",
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 28,
              height: 28,
              background: "var(--accent)",
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          </div>
          <span
            style={{
              fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
              fontWeight: 700,
              fontSize: 15,
              letterSpacing: "-0.02em",
              color: "#f1f5f9",
            }}
          >
            IntelliFlow AI
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Link
            href="/login"
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: "var(--ink-40)",
              padding: "8px 16px",
              borderRadius: 6,
              transition: "color 0.1s",
              textDecoration: "none",
            }}
          >
            Sign In
          </Link>
          <Link href="/register" className="btn btn-primary btn-sm">
            Get Started
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section
        style={{
          padding: "96px 48px 80px",
          maxWidth: 1100,
          margin: "0 auto",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 64,
            alignItems: "center",
          }}
        >
          {/* Left — editorial text */}
          <div>
            <p
              className="eyebrow"
              style={{ color: "var(--accent)", marginBottom: 16 }}
            >
              Intelligent Documentation Platform
            </p>

            <h1
              className="display-xl font-display"
              style={{ color: "#f8fafc", marginBottom: 24 }}
            >
              Your organization&apos;s knowledge,
              <br />
              <span style={{ color: "var(--ink-40)" }}>finally working together.</span>
            </h1>

            <p
              style={{
                fontSize: 17,
                lineHeight: 1.7,
                color: "var(--ink-40)",
                marginBottom: 40,
                maxWidth: 440,
              }}
            >
              IntelliFlow brings your documents, workflows, and organizational intelligence
              into a single enterprise-grade platform. Built for teams that move fast.
            </p>

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Link href="/login" className="btn btn-primary btn-lg">
                Enter Workspace →
              </Link>
              <Link
                href="/register"
                className="btn btn-ghost btn-lg"
              >
                Register Account
              </Link>
            </div>

            {/* Feature strip */}
            <div
              style={{
                display: "flex",
                gap: 24,
                marginTop: 48,
                paddingTop: 32,
                borderTop: "1px solid var(--ink-70)",
              }}
            >
              {[
                ["Document Intelligence", "AI-powered analysis"],
                ["Workflow Automation", "Approval pipelines"],
                ["Predictive Analytics", "Forward-looking insights"],
              ].map(([title, sub]) => (
                <div key={title}>
                  <p style={{ fontSize: 13, fontWeight: 600, color: "#cbd5e1", marginBottom: 2 }}>
                    {title}
                  </p>
                  <p style={{ fontSize: 12, color: "var(--ink-40)" }}>{sub}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Right — CSS document composition */}
          <div
            style={{
              position: "relative",
              height: 480,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {/* Background document stack */}
            <div
              style={{
                position: "absolute",
                right: 20,
                top: 60,
                width: 200,
                background: "var(--ink-80)",
                border: "1px solid var(--ink-70)",
                borderRadius: 10,
                padding: "16px 14px",
                transform: "rotate(3deg)",
              }}
            >
              <div style={{ height: 8, background: "var(--ink-60)", borderRadius: 4, width: "60%", marginBottom: 8 }} />
              <div style={{ height: 6, background: "var(--ink-70)", borderRadius: 3, width: "90%", marginBottom: 5 }} />
              <div style={{ height: 6, background: "var(--ink-70)", borderRadius: 3, width: "75%", marginBottom: 5 }} />
              <div style={{ height: 6, background: "var(--ink-70)", borderRadius: 3, width: "85%" }} />
            </div>

            {/* Main featured document */}
            <div
              style={{
                position: "relative",
                width: 260,
                background: "var(--ink-80)",
                border: "1px solid var(--ink-70)",
                borderRadius: 12,
                padding: "20px 18px",
                zIndex: 2,
              }}
            >
              {/* Doc type label */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                <span className="badge badge-active" style={{ fontSize: 10 }}>Active</span>
                <span style={{ fontSize: 10, color: "var(--ink-40)" }}>v2.4</span>
              </div>

              <p style={{ fontFamily: "var(--font-jakarta, sans-serif)", fontWeight: 700, fontSize: 14, color: "#f1f5f9", marginBottom: 12, letterSpacing: "-0.02em" }}>
                Engineering Architecture
                <br />Handbook
              </p>

              {/* Document preview lines */}
              <div style={{ marginBottom: 14 }}>
                {["long", "medium", "long", "short", "medium"].map((cls, i) => (
                  <div
                    key={i}
                    className={`doc-preview-line doc-preview-dark ${cls}`}
                    style={{ marginBottom: 5 }}
                  />
                ))}
              </div>

              {/* Footer */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, borderTop: "1px solid var(--ink-70)" }}>
                <span style={{ fontSize: 11, color: "var(--ink-40)" }}>Updated 2h ago</span>
                <Link
                  href="/login"
                  style={{ fontSize: 11, fontWeight: 600, color: "var(--accent)", letterSpacing: "0.01em" }}
                >
                  Open →
                </Link>
              </div>
            </div>

            {/* Workflow status card */}
            <div
              style={{
                position: "absolute",
                left: 0,
                bottom: 80,
                width: 180,
                background: "var(--ink-80)",
                border: "1px solid var(--ink-70)",
                borderRadius: 10,
                padding: "14px 12px",
                transform: "rotate(-2deg)",
                zIndex: 1,
              }}
            >
              <p className="eyebrow" style={{ marginBottom: 8 }}>Pending Review</p>
              <p style={{ fontSize: 12, fontWeight: 600, color: "#f1f5f9", marginBottom: 12 }}>
                Q3 Policy Update
              </p>
              <div style={{ display: "flex", gap: 4 }}>
                {["✓", "✓", "○", "○"].map((s, i) => (
                  <div key={i} style={{
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    background: s === "✓" ? "rgb(22 163 74 / 0.2)" : "var(--ink-70)",
                    border: `1px solid ${s === "✓" ? "#16a34a" : "var(--ink-60)"}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 8,
                    color: s === "✓" ? "#4ade80" : "var(--ink-40)",
                  }}>
                    {s}
                  </div>
                ))}
              </div>
            </div>

            {/* AI insight chip */}
            <div
              style={{
                position: "absolute",
                right: 10,
                bottom: 100,
                background: "rgb(31 92 246 / 0.12)",
                border: "1px solid rgb(31 92 246 / 0.3)",
                borderRadius: 8,
                padding: "8px 12px",
                fontSize: 11,
                color: "#93c5fd",
                fontWeight: 600,
                zIndex: 3,
              }}
            >
              ✦ AI Summary ready
            </div>
          </div>
        </div>
      </section>

      {/* Metric strip */}
      <div style={{ borderTop: "1px solid var(--ink-70)", borderBottom: "1px solid var(--ink-70)" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex" }}>
          {[
            ["Document Intelligence", "AI-powered OCR, extraction & semantic search"],
            ["Workflow Engine", "Automated approval pipelines with audit trails"],
            ["Predictive Analytics", "Revenue, attrition & churn forecasting"],
            ["Enterprise Security", "RBAC, encryption, webhooks & integrations"],
          ].map(([title, sub], i) => (
            <div
              key={title}
              style={{
                flex: 1,
                padding: "28px 32px",
                borderRight: i < 3 ? "1px solid var(--ink-70)" : "none",
              }}
            >
              <p style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", marginBottom: 4, letterSpacing: "-0.01em" }}>
                {title}
              </p>
              <p style={{ fontSize: 12, color: "var(--ink-40)", lineHeight: 1.5 }}>{sub}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <footer
        style={{
          padding: "32px 48px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderTop: "1px solid var(--ink-70)",
        }}
      >
        <span style={{ fontSize: 12, color: "var(--ink-60)" }}>
          IntelliFlow AI — Enterprise Documentation Platform
        </span>
        <div style={{ display: "flex", gap: 20 }}>
          <Link href="/login" style={{ fontSize: 12, color: "var(--ink-40)", textDecoration: "none" }}>Sign In</Link>
          <Link href="/register" style={{ fontSize: 12, color: "var(--ink-40)", textDecoration: "none" }}>Register</Link>
        </div>
      </footer>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (max-width: 768px) {
          section > div { grid-template-columns: 1fr !important; gap: 40px !important; }
          section > div > div:last-child { height: 300px !important; }
          .landing-features { flex-direction: column !important; }
        }
      `}</style>
    </div>
  );
}
