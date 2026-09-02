"use client";

import React, { useState, useEffect } from "react";
import type { Workflow, WorkflowCreateRequest, WorkflowStepCreate, WorkflowUpdateRequest } from "@/types";
import { WorkflowStepBuilder } from "./WorkflowStepBuilder";
import { createWorkflow, updateWorkflow } from "@/services/workflow.service";

interface WorkflowFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (workflow: Workflow) => void;
  workflowToEdit?: Workflow | null;
}

export const WorkflowFormModal: React.FC<WorkflowFormModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  workflowToEdit,
}) => {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [steps, setSteps] = useState<WorkflowStepCreate[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workflowToEdit) {
      setName(workflowToEdit.name);
      setDescription(workflowToEdit.description || "");
      setIsActive(workflowToEdit.is_active);
      setSteps(
        workflowToEdit.steps.map((s) => ({
          step_number: s.step_number,
          action: s.action,
          configuration: s.configuration,
          timeout: s.timeout,
          retry_count: s.retry_count,
        })),
      );
    } else {
      setName("");
      setDescription("");
      setIsActive(true);
      setSteps([
        {
          step_number: 1,
          action: "notify",
          configuration: {
            user_id: "",
            title: "Process Started",
            message: "Your workflow execution has begun.",
          },
          retry_count: 0,
        },
      ]);
    }
    setError(null);
  }, [workflowToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError("Workflow name is required.");
      return;
    }

    if (steps.length === 0) {
      setError("At least one step is required to build a workflow.");
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      if (workflowToEdit) {
        const payload: WorkflowUpdateRequest = {
          name: name.trim(),
          description: description.trim() || null,
          is_active: isActive,
          steps,
        };
        const res = await updateWorkflow(workflowToEdit.id, payload);
        if (res.success && res.data) {
          onSuccess(res.data);
          onClose();
        }
      } else {
        const payload: WorkflowCreateRequest = {
          name: name.trim(),
          description: description.trim() || null,
          steps,
        };
        const res = await createWorkflow(payload);
        if (res.success && res.data) {
          onSuccess(res.data);
          onClose();
        }
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to save workflow definition. Please check your inputs.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in overflow-y-auto">
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-3xl w-full max-w-2xl shadow-2xl overflow-hidden my-8">
        {/* Header */}
        <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold text-lg">
              ⚡
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900 dark:text-white">
                {workflowToEdit ? "Edit Workflow" : "Create Automated Workflow"}
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {workflowToEdit
                  ? "Update steps and trigger configuration."
                  : "Define multi-step sequences that execute automatically."}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 flex items-center justify-center text-gray-500 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="p-6 space-y-6 max-h-[calc(80vh-140px)] overflow-y-auto">
            {error && (
              <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
                <span>⚠️</span>
                <span>{error}</span>
              </div>
            )}

            {/* Workflow Name & Description */}
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-1.5">
                  Workflow Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  maxLength={200}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Employee Onboarding Document Pipeline"
                  className="w-full px-4 py-2.5 text-sm bg-gray-50 dark:bg-gray-800/80 border border-gray-200 dark:border-gray-700 rounded-xl text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-1.5">
                  Description
                </label>
                <textarea
                  rows={2}
                  maxLength={2000}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Briefly describe what this workflow automates..."
                  className="w-full px-4 py-2.5 text-sm bg-gray-50 dark:bg-gray-800/80 border border-gray-200 dark:border-gray-700 rounded-xl text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                />
              </div>

              {workflowToEdit && (
                <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-800">
                  <div>
                    <span className="text-xs font-semibold text-gray-900 dark:text-white block">
                      Workflow Active Status
                    </span>
                    <span className="text-[11px] text-gray-500 dark:text-gray-400">
                      Inactive workflows cannot be triggered manually or automatically.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsActive(!isActive)}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      isActive ? "bg-blue-600" : "bg-gray-300 dark:bg-gray-700"
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                        isActive ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>
              )}
            </div>

            {/* Step Builder */}
            <div className="pt-2 border-t border-gray-200 dark:border-gray-800">
              <WorkflowStepBuilder steps={steps} onChange={setSteps} />
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-800 flex items-center justify-end gap-3 bg-gray-50 dark:bg-gray-900/50">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-xl transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-md shadow-blue-600/20 hover:shadow-lg hover:shadow-blue-600/30 transition-all flex items-center gap-2 disabled:opacity-50"
            >
              {submitting && (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              <span>{workflowToEdit ? "Save Changes" : "Create Workflow"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
