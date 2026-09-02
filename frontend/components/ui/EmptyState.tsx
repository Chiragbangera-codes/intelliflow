"use client";

import React from "react";

interface EmptyStateProps {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  actionLabel,
  onAction,
}) => {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "64px 32px",
        textAlign: "center",
      }}
    >
      {/* Document icon — CSS composed */}
      <div
        style={{
          width: 48,
          height: 60,
          background: "var(--ink-80)",
          border: "1px solid var(--ink-70)",
          borderRadius: 8,
          position: "relative",
          marginBottom: 24,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: 4,
          padding: "0 8px",
        }}
      >
        {/* Folded corner */}
        <div
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            width: 14,
            height: 14,
            background: "var(--ink-90)",
            borderBottomLeftRadius: 4,
            borderLeft: "1px solid var(--ink-70)",
            borderBottom: "1px solid var(--ink-70)",
          }}
        />
        {[80, 60, 80, 50].map((w, i) => (
          <div
            key={i}
            style={{
              height: 4,
              width: `${w}%`,
              background: "var(--ink-70)",
              borderRadius: 2,
            }}
          />
        ))}
      </div>

      <h3
        style={{
          fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
          fontSize: 16,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          color: "#f1f5f9",
          margin: "0 0 8px",
        }}
      >
        {title}
      </h3>

      {description && (
        <p
          style={{
            fontSize: 13,
            color: "var(--ink-40)",
            lineHeight: 1.6,
            maxWidth: 320,
            margin: "0 0 24px",
          }}
        >
          {description}
        </p>
      )}

      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="btn btn-primary btn-sm"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};
