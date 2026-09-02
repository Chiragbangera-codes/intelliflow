"use client";

import React from "react";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = "md",
  message,
}) => {
  const sz = size === "sm" ? 16 : size === "lg" ? 32 : 22;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        padding: size === "lg" ? "48px 0" : "24px 0",
      }}
    >
      <div
        style={{
          width: sz,
          height: sz,
          border: `2px solid var(--ink-70)`,
          borderTopColor: "var(--accent)",
          borderRadius: "50%",
          animation: "spin 0.75s linear infinite",
          flexShrink: 0,
        }}
      />
      {message && (
        <p
          style={{
            fontSize: 13,
            color: "var(--ink-40)",
            margin: 0,
            letterSpacing: "0.01em",
          }}
        >
          {message}
        </p>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};
