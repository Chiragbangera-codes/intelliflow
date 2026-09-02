"use client";

import React from "react";
import type { ExecutionStatusType } from "@/types";

interface ExecutionStatusBadgeProps {
  status: ExecutionStatusType | string;
  size?: "sm" | "md" | "lg";
}

export const ExecutionStatusBadge: React.FC<ExecutionStatusBadgeProps> = ({
  status,
  size = "md",
}) => {
  const normalized = status.toLowerCase();

  const configs: Record<
    string,
    { label: string; bg: string; text: string; border: string; dot: string; pulse?: boolean }
  > = {
    pending: {
      label: "Pending",
      bg: "bg-amber-50 dark:bg-amber-950/40",
      text: "text-amber-700 dark:text-amber-300",
      border: "border-amber-200 dark:border-amber-800",
      dot: "bg-amber-500",
      pulse: true,
    },
    running: {
      label: "Running",
      bg: "bg-blue-50 dark:bg-blue-950/40",
      text: "text-blue-700 dark:text-blue-300",
      border: "border-blue-200 dark:border-blue-800",
      dot: "bg-blue-500",
      pulse: true,
    },
    waiting_approval: {
      label: "Waiting Approval",
      bg: "bg-purple-50 dark:bg-purple-950/40",
      text: "text-purple-700 dark:text-purple-300",
      border: "border-purple-200 dark:border-purple-800",
      dot: "bg-purple-500",
      pulse: true,
    },
    completed: {
      label: "Completed",
      bg: "bg-emerald-50 dark:bg-emerald-950/40",
      text: "text-emerald-700 dark:text-emerald-300",
      border: "border-emerald-200 dark:border-emerald-800",
      dot: "bg-emerald-500",
    },
    failed: {
      label: "Failed",
      bg: "bg-rose-50 dark:bg-rose-950/40",
      text: "text-rose-700 dark:text-rose-300",
      border: "border-rose-200 dark:border-rose-800",
      dot: "bg-rose-500",
    },
    rejected: {
      label: "Rejected",
      bg: "bg-slate-100 dark:bg-slate-800",
      text: "text-slate-700 dark:text-slate-300",
      border: "border-slate-300 dark:border-slate-700",
      dot: "bg-slate-400",
    },
  };

  const current = configs[normalized] || {
    label: status,
    bg: "bg-gray-100 dark:bg-gray-800",
    text: "text-gray-700 dark:text-gray-300",
    border: "border-gray-200 dark:border-gray-700",
    dot: "bg-gray-400",
  };

  const sizeClasses = {
    sm: "px-2 py-0.5 text-[11px]",
    md: "px-2.5 py-1 text-xs",
    lg: "px-3 py-1.5 text-sm",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${current.bg} ${current.text} ${current.border} ${sizeClasses[size]}`}
    >
      <span className="relative flex h-2 w-2">
        {current.pulse && (
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full ${current.dot} opacity-75`}
          />
        )}
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${current.dot}`}
        />
      </span>
      <span>{current.label}</span>
    </span>
  );
};
