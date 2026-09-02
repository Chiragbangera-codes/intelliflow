"use client";

import React from "react";

export interface DocumentPreviewProps {
  title: string;
  fileType?: string;
  version?: number | string;
  status?: string;
  category?: string;
  updatedAt?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
  onClick?: () => void;
}

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({
  title,
  fileType = "DOC",
  version = 1,
  status = "active",
  category,
  updatedAt,
  size = "md",
  className = "",
  onClick,
}) => {
  const width = size === "sm" ? 180 : size === "lg" ? 280 : 220;
  const ext = fileType.replace(/^\./, "").toUpperCase().slice(0, 4);

  return (
    <div
      onClick={onClick}
      className={`doc-card ${onClick ? "cursor-pointer hover-lift" : ""} ${className}`}
      style={{
        width,
        background: "var(--ink-80)",
        border: "1px solid var(--ink-70)",
        borderRadius: 10,
        padding: "16px 14px",
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        minHeight: size === "sm" ? 130 : 160,
      }}
    >
      {/* Dog-ear corner fold */}
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          width: 16,
          height: 16,
          background: "var(--ink-90)",
          borderBottomLeftRadius: 5,
          borderLeft: "1px solid var(--ink-70)",
          borderBottom: "1px solid var(--ink-70)",
        }}
      />

      {/* Top meta strip */}
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 10,
            paddingRight: 14,
          }}
        >
          <span
            style={{
              fontSize: 9,
              fontWeight: 800,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              padding: "2px 5px",
              borderRadius: 3,
              background: "var(--ink-70)",
              color: "#93c5fd",
              fontFamily: "monospace",
            }}
          >
            {ext}
          </span>
          <span
            style={{
              fontSize: 10,
              color: "var(--ink-40)",
              fontFamily: "monospace",
            }}
          >
            v{version}
          </span>
        </div>

        {/* Title */}
        <p
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: "#f1f5f9",
            margin: "0 0 10px",
            lineHeight: 1.3,
            letterSpacing: "-0.015em",
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {title}
        </p>

        {/* CSS simulated content lines */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 12 }}>
          <div style={{ height: 4, background: "var(--ink-70)", borderRadius: 2, width: "85%" }} />
          <div style={{ height: 4, background: "var(--ink-70)", borderRadius: 2, width: "65%" }} />
          <div style={{ height: 4, background: "var(--ink-70)", borderRadius: 2, width: "95%" }} />
        </div>
      </div>

      {/* Bottom meta */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: "1px solid var(--ink-70)",
          paddingTop: 8,
          marginTop: "auto",
        }}
      >
        <span
          className={`badge ${
            status === "active"
              ? "badge-active"
              : status === "draft"
              ? "badge-draft"
              : "badge-archived"
          }`}
          style={{ fontSize: 9, padding: "1px 5px" }}
        >
          {status}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {category && (
            <span style={{ fontSize: 9, color: "var(--ink-40)" }}>{category}</span>
          )}
          {updatedAt && (
            <span style={{ fontSize: 10, color: "var(--ink-40)" }}>{updatedAt}</span>
          )}
        </div>
      </div>
    </div>
  );
};
