import React from "react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        minHeight: "100vh",
        width: "100%",
        display: "flex",
        background: "var(--ink)",
      }}
    >
      {/* Left panel — editorial brand */}
      <div
        style={{
          flex: "0 0 42%",
          background: "var(--ink-90)",
          borderRight: "1px solid var(--ink-70)",
          display: "flex",
          flexDirection: "column",
          padding: "48px 52px",
          position: "relative",
          overflow: "hidden",
        }}
        className="auth-brand-panel"
      >
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "auto" }}>
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

        {/* Hero text — editorial large heading */}
        <div style={{ marginTop: "auto", paddingBottom: 40 }}>
          <p
            className="eyebrow"
            style={{ color: "var(--accent)", marginBottom: 20 }}
          >
            Document Intelligence
          </p>
          <h1
            style={{
              fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
              fontSize: "clamp(2rem, 3.5vw, 2.75rem)",
              fontWeight: 800,
              lineHeight: 1.1,
              letterSpacing: "-0.035em",
              color: "#f8fafc",
              marginBottom: 20,
            }}
          >
            The platform where
            <br />
            <span style={{ color: "var(--ink-40)" }}>knowledge becomes</span>
            <br />
            intelligence.
          </h1>
          <p
            style={{
              fontSize: 14,
              lineHeight: 1.7,
              color: "var(--ink-40)",
              maxWidth: 340,
            }}
          >
            Documents, workflows, approvals and predictive insights —
            unified into one enterprise-grade workspace.
          </p>

          {/* CSS Document decoration */}
          <div style={{ marginTop: 40, display: "flex", gap: 12 }}>
            <div
              style={{
                background: "var(--ink-80)",
                border: "1px solid var(--ink-70)",
                borderRadius: 10,
                padding: "14px 12px",
                width: 130,
              }}
            >
              <p className="eyebrow" style={{ marginBottom: 8 }}>Policy Doc</p>
              <div style={{ height: 6, background: "var(--ink-70)", borderRadius: 3, width: "80%", marginBottom: 4 }} />
              <div style={{ height: 6, background: "var(--ink-70)", borderRadius: 3, width: "60%", marginBottom: 4 }} />
              <div style={{ height: 6, background: "var(--ink-70)", borderRadius: 3, width: "90%" }} />
              <div style={{ marginTop: 10, display: "flex", gap: 4 }}>
                <span className="badge badge-active" style={{ fontSize: 9 }}>Active</span>
                <span style={{ fontSize: 10, color: "var(--ink-40)" }}>v3.1</span>
              </div>
            </div>
            <div
              style={{
                background: "var(--ink-80)",
                border: "1px solid var(--ink-70)",
                borderRadius: 10,
                padding: "14px 12px",
                width: 130,
                transform: "translateY(12px)",
              }}
            >
              <p className="eyebrow" style={{ marginBottom: 8 }}>Workflow</p>
              <p style={{ fontSize: 12, fontWeight: 600, color: "#f1f5f9", marginBottom: 8 }}>HR Handbook</p>
              <div style={{ fontSize: 10, color: "#4ade80" }}>Review complete</div>
            </div>
          </div>
        </div>
      </div>

      {/* Right panel — form */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 40px",
        }}
      >
        {children}
      </div>

      <style>{`
        @media (max-width: 768px) {
          .auth-brand-panel { display: none !important; }
        }
      `}</style>
    </div>
  );
}
