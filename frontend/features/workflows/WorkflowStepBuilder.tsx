"use client";

import React from "react";
import type { WorkflowActionType, WorkflowStepCreate } from "@/types";

interface WorkflowStepBuilderProps {
  steps: WorkflowStepCreate[];
  onChange: (steps: WorkflowStepCreate[]) => void;
}

const ACTION_CONFIGS: Record<
  WorkflowActionType,
  { label: string; description: string; icon: string; color: string }
> = {
  notify: {
    label: "In-App Notification",
    description: "Send a notification banner to a specific team member",
    icon: "🔔",
    color: "from-blue-500/10 to-indigo-500/10 border-blue-500/30 text-blue-500",
  },
  send_email: {
    label: "Send Email (SMTP)",
    description: "Dispatch an external email message via configured SMTP",
    icon: "✉️",
    color: "from-emerald-500/10 to-teal-500/10 border-emerald-500/30 text-emerald-500",
  },
  archive_document: {
    label: "Archive Document",
    description: "Soft-delete a document record with audit trail tracking",
    icon: "📁",
    color: "from-amber-500/10 to-orange-500/10 border-amber-500/30 text-amber-500",
  },
  approve: {
    label: "Management Approval Gate",
    description: "Pause execution until a manager clicks Approve or Reject",
    icon: "🛡️",
    color: "from-purple-500/10 to-pink-500/10 border-purple-500/30 text-purple-500",
  },
  delay: {
    label: "Timer Delay",
    description: "Pause execution for a designated number of seconds (1–300)",
    icon: "⏱️",
    color: "from-cyan-500/10 to-sky-500/10 border-cyan-500/30 text-cyan-500",
  },
};

export const WorkflowStepBuilder: React.FC<WorkflowStepBuilderProps> = ({
  steps,
  onChange,
}) => {
  const addStep = (action: WorkflowActionType = "notify") => {
    let initialConfig: Record<string, unknown> = {};
    if (action === "notify") {
      initialConfig = { user_id: "", title: "", message: "" };
    } else if (action === "send_email") {
      initialConfig = { to: "", subject: "", body: "" };
    } else if (action === "archive_document") {
      initialConfig = { document_id: "" };
    } else if (action === "delay") {
      initialConfig = { seconds: 5 };
    } else if (action === "approve") {
      initialConfig = { approver_user_id: "" };
    }

    const newStep: WorkflowStepCreate = {
      step_number: steps.length + 1,
      action,
      configuration: initialConfig,
      timeout: null,
      retry_count: 0,
    };
    onChange([...steps, newStep]);
  };

  const removeStep = (index: number) => {
    const updated = steps
      .filter((_, i) => i !== index)
      .map((s, idx) => ({ ...s, step_number: idx + 1 }));
    onChange(updated);
  };

  const moveStep = (index: number, direction: "up" | "down") => {
    const targetIdx = direction === "up" ? index - 1 : index + 1;
    if (targetIdx < 0 || targetIdx >= steps.length) return;

    const reordered = [...steps];
    const temp = reordered[index];
    reordered[index] = reordered[targetIdx];
    reordered[targetIdx] = temp;

    const normalized = reordered.map((s, idx) => ({
      ...s,
      step_number: idx + 1,
    }));
    onChange(normalized);
  };

  const updateStepAction = (index: number, newAction: WorkflowActionType) => {
    let newConfig: Record<string, unknown> = {};
    if (newAction === "notify") {
      newConfig = { user_id: "", title: "", message: "" };
    } else if (newAction === "send_email") {
      newConfig = { to: "", subject: "", body: "" };
    } else if (newAction === "archive_document") {
      newConfig = { document_id: "" };
    } else if (newAction === "delay") {
      newConfig = { seconds: 5 };
    } else if (newAction === "approve") {
      newConfig = { approver_user_id: "" };
    }

    const updated = [...steps];
    updated[index] = {
      ...updated[index],
      action: newAction,
      configuration: newConfig,
    };
    onChange(updated);
  };

  const updateConfigValue = (index: number, key: string, value: unknown) => {
    const updated = [...steps];
    const currentConfig = (updated[index].configuration ?? {}) as Record<string, unknown>;
    updated[index] = {
      ...updated[index],
      configuration: {
        ...currentConfig,
        [key]: value,
      },
    };
    onChange(updated);
  };

  const updateStepField = (
    index: number,
    field: "timeout" | "retry_count",
    value: number | null,
  ) => {
    const updated = [...steps];
    updated[index] = {
      ...updated[index],
      [field]: value,
    };
    onChange(updated);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
            Workflow Steps Sequence ({steps.length})
          </h4>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Define sequential operations executed when this workflow runs.
          </p>
        </div>
      </div>

      {steps.length === 0 ? (
        <div className="p-8 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-2xl text-center">
          <div className="w-12 h-12 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center mx-auto mb-3 text-2xl">
            ⚡
          </div>
          <p className="text-sm font-medium text-gray-900 dark:text-white">
            No steps configured
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-sm mx-auto">
            Add at least one step to build an automated workflow.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2 mt-4">
            {(Object.keys(ACTION_CONFIGS) as WorkflowActionType[]).map((actionKey) => (
              <button
                key={actionKey}
                type="button"
                onClick={() => addStep(actionKey)}
                className="px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs font-medium transition-all flex items-center gap-1.5"
              >
                <span>{ACTION_CONFIGS[actionKey].icon}</span>
                <span>{ACTION_CONFIGS[actionKey].label}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {steps.map((step, idx) => {
            const conf = ACTION_CONFIGS[step.action] || ACTION_CONFIGS.notify;
            const configObj = (step.configuration ?? {}) as Record<string, unknown>;

            return (
              <div
                key={idx}
                className="p-4 rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm relative group hover:border-gray-300 dark:hover:border-gray-700 transition-all"
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-lg bg-gray-900 dark:bg-white text-white dark:text-gray-900 text-xs font-bold flex items-center justify-center shrink-0">
                      {step.step_number}
                    </span>
                    <div>
                      <select
                        value={step.action}
                        onChange={(e) =>
                          updateStepAction(idx, e.target.value as WorkflowActionType)
                        }
                        className="text-xs font-bold text-gray-900 dark:text-white bg-transparent border-b border-gray-300 dark:border-gray-700 pb-0.5 focus:outline-none focus:border-blue-500"
                      >
                        {(Object.keys(ACTION_CONFIGS) as WorkflowActionType[]).map(
                          (act) => (
                            <option key={act} value={act} className="dark:bg-gray-900">
                              {ACTION_CONFIGS[act].icon} {ACTION_CONFIGS[act].label}
                            </option>
                          ),
                        )}
                      </select>
                      <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
                        {conf.description}
                      </p>
                    </div>
                  </div>

                  {/* Actions (move, remove) */}
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={idx === 0}
                      onClick={() => moveStep(idx, "up")}
                      className="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 disabled:opacity-30"
                      title="Move up"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      disabled={idx === steps.length - 1}
                      onClick={() => moveStep(idx, "down")}
                      className="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 disabled:opacity-30"
                      title="Move down"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      onClick={() => removeStep(idx)}
                      className="p-1 rounded-lg text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/50"
                      title="Remove step"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* Dynamic Configuration Form */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-gray-100 dark:border-gray-800">
                  {step.action === "notify" && (
                    <>
                      <div className="sm:col-span-2">
                        <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                          Target User UUID <span className="text-rose-500">*</span>
                        </label>
                        <input
                          type="text"
                          required
                          value={(configObj.user_id as string) ?? ""}
                          onChange={(e) => updateConfigValue(idx, "user_id", e.target.value)}
                          placeholder="e.g. 00000000-0000-0000-0000-000000000001"
                          className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                          Notification Title <span className="text-rose-500">*</span>
                        </label>
                        <input
                          type="text"
                          required
                          value={(configObj.title as string) ?? ""}
                          onChange={(e) => updateConfigValue(idx, "title", e.target.value)}
                          placeholder="e.g. Action Required"
                          className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                          Message Body <span className="text-rose-500">*</span>
                        </label>
                        <input
                          type="text"
                          required
                          value={(configObj.message as string) ?? ""}
                          onChange={(e) => updateConfigValue(idx, "message", e.target.value)}
                          placeholder="e.g. Workflow step completed successfully"
                          className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                        />
                      </div>
                    </>
                  )}

                  {step.action === "send_email" && (
                    <>
                      <div>
                        <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                          Recipient Email <span className="text-rose-500">*</span>
                        </label>
                        <input
                          type="email"
                          required
                          value={(configObj.to as string) ?? ""}
                          onChange={(e) => updateConfigValue(idx, "to", e.target.value)}
                          placeholder="user@example.com"
                          className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                          Subject <span className="text-rose-500">*</span>
                        </label>
                        <input
                          type="text"
                          required
                          value={(configObj.subject as string) ?? ""}
                          onChange={(e) => updateConfigValue(idx, "subject", e.target.value)}
                          placeholder="e.g. Automated Alert"
                          className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                          Email Body <span className="text-rose-500">*</span>
                        </label>
                        <textarea
                          rows={2}
                          required
                          value={(configObj.body as string) ?? ""}
                          onChange={(e) => updateConfigValue(idx, "body", e.target.value)}
                          placeholder="Plain text email content..."
                          className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                        />
                      </div>
                    </>
                  )}

                  {step.action === "archive_document" && (
                    <div className="sm:col-span-2">
                      <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                        Document UUID to Archive <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        value={(configObj.document_id as string) ?? ""}
                        onChange={(e) => updateConfigValue(idx, "document_id", e.target.value)}
                        placeholder="e.g. a3c914e2-6712-4fe0-94d1-..."
                        className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                      />
                    </div>
                  )}

                  {step.action === "delay" && (
                    <div>
                      <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                        Delay Seconds (1–300) <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={300}
                        required
                        value={(configObj.seconds as number) ?? 5}
                        onChange={(e) =>
                          updateConfigValue(idx, "seconds", parseInt(e.target.value, 10) || 1)
                        }
                        className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                      />
                    </div>
                  )}

                  {step.action === "approve" && (
                    <div className="sm:col-span-2">
                      <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                        Designated Approver UUID (Optional)
                      </label>
                      <input
                        type="text"
                        value={(configObj.approver_user_id as string) ?? ""}
                        onChange={(e) =>
                          updateConfigValue(idx, "approver_user_id", e.target.value)
                        }
                        placeholder="Leave blank for any manager/admin"
                        className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                      />
                    </div>
                  )}

                  {/* Step retries */}
                  <div>
                    <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
                      Retries on Failure (0–5)
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={5}
                      value={step.retry_count ?? 0}
                      onChange={(e) =>
                        updateStepField(idx, "retry_count", parseInt(e.target.value, 10) || 0)
                      }
                      className="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white"
                    />
                  </div>
                </div>
              </div>
            );
          })}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={() => addStep("notify")}
              className="px-3 py-1.5 rounded-xl border border-dashed border-gray-300 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 text-xs font-semibold text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-all flex items-center gap-1.5"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Add Next Step</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
