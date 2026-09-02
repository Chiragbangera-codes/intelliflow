"use client";

import React from "react";

type BadgeVariant =
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "neutral";

interface BadgeProps {
  variant?: BadgeVariant;
  size?: "sm" | "md";
  children: React.ReactNode;
  className?: string;
}

const VARIANT_MAP: Record<BadgeVariant, string> = {
  primary: "badge-internal",
  success: "badge-active",
  warning: "badge-archived",
  danger: "badge-expired",
  info: "badge-public",
  neutral: "badge-draft",
};

export const Badge: React.FC<BadgeProps> = ({
  variant = "neutral",
  children,
  className = "",
}) => {
  return (
    <span className={`badge ${VARIANT_MAP[variant]} ${className}`}>
      {children}
    </span>
  );
};
