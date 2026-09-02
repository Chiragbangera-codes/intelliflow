"use client";

import React from "react";

export interface MetricItem {
  label: string;
  value: string | number;
  sub?: string;
  tag?: string;
}

export interface MetricStripProps {
  metrics: MetricItem[];
  className?: string;
  style?: React.CSSProperties;
}

export const MetricStrip: React.FC<MetricStripProps> = ({
  metrics,
  className = "",
  style,
}) => {
  return (
    <div
      className={`metric-strip ${className}`}
      style={{
        display: "flex",
        border: "1px solid var(--ink-70)",
        borderRadius: 12,
        overflow: "hidden",
        marginBottom: 36,
        background: "var(--ink-90)",
        ...style,
      }}
    >
      {metrics.map((item, idx) => (
        <div
          key={item.label}
          style={{
            flex: 1,
            padding: "20px 24px",
            borderRight:
              idx < metrics.length - 1 ? "1px solid var(--ink-70)" : "none",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
            <span
              style={{
                fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
                fontSize: typeof item.value === "number" ? "clamp(1.5rem, 2.5vw, 2.25rem)" : "clamp(1.25rem, 2vw, 1.75rem)",
                fontWeight: 800,
                letterSpacing: "-0.03em",
                color: "#f1f5f9",
                lineHeight: 1,
              }}
            >
              {typeof item.value === "number" ? item.value.toLocaleString() : item.value}
            </span>
            {item.tag && (
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: "var(--accent)",
                  background: "rgb(31 92 246 / 0.1)",
                  padding: "2px 6px",
                  borderRadius: 4,
                }}
              >
                {item.tag}
              </span>
            )}
          </div>
          <span
            style={{
              display: "block",
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--ink-40)",
            }}
          >
            {item.label}
          </span>
          {item.sub && (
            <span
              style={{
                display: "block",
                fontSize: 11,
                color: "var(--ink-60)",
                marginTop: 3,
              }}
            >
              {item.sub}
            </span>
          )}
        </div>
      ))}
    </div>
  );
};
