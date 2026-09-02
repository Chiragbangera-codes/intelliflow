"use client";

import React from "react";

export interface SectionHeaderProps {
  eyebrow?: string;
  title: string;
  accentTitle?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  eyebrow,
  title,
  accentTitle,
  description,
  action,
  className = "",
}) => {
  return (
    <div
      className={className}
      style={{
        marginBottom: 36,
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "space-between",
        gap: 16,
        flexWrap: "wrap",
      }}
    >
      <div>
        {eyebrow && (
          <p
            className="eyebrow"
            style={{ color: "var(--accent)", marginBottom: 12 }}
          >
            {eyebrow}
          </p>
        )}
        <h1
          style={{
            fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
            fontSize: "clamp(1.75rem, 3vw, 2.5rem)",
            fontWeight: 800,
            letterSpacing: "-0.04em",
            color: "#f8fafc",
            lineHeight: 1.1,
            margin: 0,
          }}
        >
          {title}
          {accentTitle && (
            <>
              <br />
              <span style={{ color: "var(--ink-40)" }}>{accentTitle}</span>
            </>
          )}
        </h1>
        {description && (
          <p
            style={{
              marginTop: 10,
              fontSize: 14,
              color: "var(--ink-40)",
              maxWidth: 580,
              lineHeight: 1.6,
            }}
          >
            {description}
          </p>
        )}
      </div>

      {action && (
        <div style={{ flexShrink: 0 }}>
          {action}
        </div>
      )}
    </div>
  );
};
