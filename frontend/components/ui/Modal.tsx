"use client";

import React, { useEffect } from "react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: "sm" | "md" | "lg";
  /** @deprecated Use size instead. Kept for backward compatibility. */
  maxWidth?: string;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  size = "md",
}) => {
  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  // Prevent body scroll when open
  useEffect(() => {
    document.body.style.overflow = isOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  if (!isOpen) return null;

  const maxWidth =
    size === "sm" ? 400 : size === "lg" ? 680 : 520;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? "modal-title" : undefined}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgb(0 0 0 / 0.7)",
          backdropFilter: "blur(4px)",
        }}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        style={{
          position: "relative",
          width: "100%",
          maxWidth,
          background: "var(--ink-80)",
          border: "1px solid var(--ink-70)",
          borderRadius: 12,
          boxShadow: "0 24px 64px rgb(0 0 0 / 0.4)",
          overflow: "hidden",
          animation: "modalIn 0.15s ease",
        }}
      >
        {/* Header */}
        {title && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "18px 24px",
              borderBottom: "1px solid var(--ink-70)",
            }}
          >
            <h2
              id="modal-title"
              style={{
                fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
                fontSize: 16,
                fontWeight: 700,
                letterSpacing: "-0.02em",
                color: "#f1f5f9",
                margin: 0,
              }}
            >
              {title}
            </h2>
            <button
              onClick={onClose}
              aria-label="Close"
              style={{
                width: 28,
                height: 28,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "transparent",
                border: "none",
                borderRadius: 6,
                color: "var(--ink-40)",
                cursor: "pointer",
                transition: "background 0.1s, color 0.1s",
                padding: 0,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--ink-70)";
                e.currentTarget.style.color = "#f1f5f9";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--ink-40)";
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        )}

        {/* Body */}
        <div style={{ padding: "24px" }}>
          {children}
        </div>
      </div>

      <style>{`
        @keyframes modalIn {
          from { opacity: 0; transform: translateY(8px) scale(0.98); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
};
