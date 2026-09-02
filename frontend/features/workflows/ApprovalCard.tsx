"use client";

import React, { useState } from "react";
import type { WorkflowExecution } from "@/types";
import { approveExecution } from "@/services/workflow.service";

interface ApprovalCardProps {
  execution: WorkflowExecution;
  onDecisionSubmitted: (updated: WorkflowExecution) => void;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  execution,
  onDecisionSubmitted,
}) => {
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDecision = async (action: "approve" | "reject") => {
    try {
      setSubmitting(action);
      setError(null);
      const res = await approveExecution(execution.id, {
        action,
        comment: comment.trim() || undefined,
      });
      if (res.success && res.data) {
        onDecisionSubmitted(res.data);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to record approval decision";
      setError(msg);
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="p-6 rounded-2xl bg-gradient-to-br from-purple-900/10 via-indigo-900/10 to-blue-900/10 border-2 border-purple-500/30 dark:border-purple-500/20 shadow-lg backdrop-blur-sm">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-600 dark:text-purple-400 shrink-0 shadow-inner">
          <svg className="w-6 h-6 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
        </div>

        <div className="flex-1 space-y-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300 text-[11px] font-bold uppercase tracking-wider">
                Action Required
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                Execution paused at step {((execution.logs?.resume_from_step ?? 0) + 1)}
              </span>
            </div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mt-1">
              Workflow Approval Required
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5">
              This workflow execution is paused awaiting a management decision. Approving will continue remaining steps; rejecting will abort the execution immediately.
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              Decision Note (Optional)
            </label>
            <input
              type="text"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="e.g. Budget approved for Q3..."
              disabled={submitting !== null}
              className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            />
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={() => handleDecision("approve")}
              disabled={submitting !== null}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold shadow-md shadow-emerald-600/20 hover:shadow-lg hover:shadow-emerald-600/30 transition-all flex items-center gap-2 disabled:opacity-50"
            >
              {submitting === "approve" ? (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
              <span>Approve &amp; Resume</span>
            </button>

            <button
              onClick={() => handleDecision("reject")}
              disabled={submitting !== null}
              className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold shadow-md shadow-rose-600/20 hover:shadow-lg hover:shadow-rose-600/30 transition-all flex items-center gap-2 disabled:opacity-50"
            >
              {submitting === "reject" ? (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              )}
              <span>Reject Execution</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
