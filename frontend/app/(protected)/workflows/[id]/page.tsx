"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useAuthStore } from "@/store/auth.store";
import type { Workflow, WorkflowExecution } from "@/types";
import {
  getWorkflow,
  listExecutions,
  triggerWorkflow,
} from "@/services/workflow.service";
import {
  ApprovalCard,
  ExecutionStatusBadge,
  WorkflowFormModal,
} from "@/features/workflows";

export default function WorkflowDetailPage() {
  const params = useParams();
  const router = useRouter();
  const workflowId = params?.id as string;
  const { user } = useAuthStore();

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [selectedExecution, setSelectedExecution] = useState<WorkflowExecution | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const canManage = user?.role === "admin" || user?.role === "manager";
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const fetchWorkflow = useCallback(async () => {
    if (!workflowId) return;
    try {
      const res = await getWorkflow(workflowId);
      if (res.success && res.data) {
        setWorkflow(res.data);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load workflow";
      setError(msg);
    }
  }, [workflowId]);

  const fetchExecutions = useCallback(async () => {
    if (!workflowId) return;
    try {
      const res = await listExecutions(workflowId, 1, 50);
      if (res.success && res.data) {
        setExecutions(res.data);
      }
    } catch (err: unknown) {
      console.error("Failed to fetch executions:", err);
    }
  }, [workflowId]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchWorkflow(), fetchExecutions()]);
      setLoading(false);
    };
    init();
  }, [fetchWorkflow, fetchExecutions]);

  // Polling setup: if any execution is pending, running, or waiting_approval, poll every 3s
  useEffect(() => {
    const hasActive = executions.some(
      (e) =>
        e.status === "pending" ||
        e.status === "running" ||
        e.status === "waiting_approval",
    );

    if (hasActive) {
      pollingRef.current = setInterval(() => {
        fetchExecutions();
      }, 3000);
    } else if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [executions, fetchExecutions]);

  const handleRun = async () => {
    if (!workflow) return;
    try {
      setRunning(true);
      const res = await triggerWorkflow(workflow.id);
      if (res.success && res.data) {
        setToastMessage(`Execution enqueued! ID: ${res.data.execution_id.slice(0, 8)}...`);
        setTimeout(() => setToastMessage(null), 4000);
        await fetchExecutions();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to trigger workflow execution";
      setError(msg);
    } finally {
      setRunning(false);
    }
  };

  const activeExecution = executions.find(
    (e) =>
      e.status === "waiting_approval" ||
      e.status === "running" ||
      e.status === "pending",
  );

  const getStepIcon = (action: string) => {
    switch (action) {
      case "notify":
        return "🔔";
      case "send_email":
        return "✉️";
      case "archive_document":
        return "📁";
      case "approve":
        return "🛡️";
      case "delay":
        return "⏱️";
      default:
        return "⚡";
    }
  };

  if (loading) {
    return (
      <DashboardLayout title="Workflow Pipeline" description="Loading workflow details...">
        <LoadingSpinner message="Loading pipeline configuration..." />
      </DashboardLayout>
    );
  }

  if (error || !workflow) {
    return (
      <DashboardLayout title="Workflow Error" description="Unable to load workflow">
        <div className="p-6 rounded-3xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300">
          <p className="font-bold text-base">Error Loading Workflow</p>
          <p className="text-sm mt-1">{error || "Workflow not found."}</p>
          <button
            onClick={() => router.push("/workflows")}
            className="mt-4 px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-md transition-all"
          >
            ← Back to Workflows
          </button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title={workflow.name}
      description={workflow.description || "Automated multi-step workflow pipeline."}
    >
      <div className="space-y-8">
        {/* Breadcrumb & Actions Bar */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-2 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <Link href="/workflows" className="hover:text-blue-600 transition-colors">
              Workflows
            </Link>
            <span>/</span>
            <span className="text-gray-900 dark:text-white font-medium truncate max-w-xs">
              {workflow.name}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span
              className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                workflow.is_active
                  ? "bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
              }`}
            >
              {workflow.is_active ? "🟢 Active" : "⚪ Disabled"}
            </span>

            {canManage && (
              <button
                onClick={() => setIsEditModalOpen(true)}
                className="px-4 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs font-semibold transition-all"
              >
                Edit Steps
              </button>
            )}

            {canManage && (
              <button
                onClick={handleRun}
                disabled={!workflow.is_active || running}
                className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-800 text-white text-xs font-bold shadow-md shadow-blue-600/20 hover:shadow-lg transition-all flex items-center gap-2"
              >
                {running ? (
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                )}
                <span>Run Pipeline</span>
              </button>
            )}
          </div>
        </div>

        {/* Toast Notification */}
        {toastMessage && (
          <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-sm font-semibold flex items-center justify-between shadow-lg backdrop-blur-sm animate-fade-in">
            <div className="flex items-center gap-2">
              <span>✨</span>
              <span>{toastMessage}</span>
            </div>
            <button onClick={() => setToastMessage(null)} className="text-emerald-500 hover:text-emerald-700">
              ✕
            </button>
          </div>
        )}

        {/* Active Approval Banner (if waiting) */}
        {activeExecution && activeExecution.status === "waiting_approval" && (
          <ApprovalCard
            execution={activeExecution}
            onDecisionSubmitted={(updated) => {
              setExecutions((prev) =>
                prev.map((e) => (e.id === updated.id ? updated : e)),
              );
              setToastMessage("Approval decision recorded. Resuming execution...");
              setTimeout(() => setToastMessage(null), 4000);
            }}
          />
        )}

        {/* Visual Pipeline Sequence Graph */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-gray-900 dark:text-white">
                Pipeline Architecture ({workflow.steps.length} Steps)
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Execution flows sequentially from step 1 through step {workflow.steps.length}.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {workflow.steps.map((step) => (
              <div

                key={step.id}
                className="p-5 rounded-3xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm relative group hover:border-blue-500 dark:hover:border-blue-500 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span className="w-7 h-7 rounded-xl bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400 text-xs font-bold flex items-center justify-center border border-blue-200 dark:border-blue-800">
                      #{step.step_number}
                    </span>
                    <span className="text-2xl">{getStepIcon(step.action)}</span>
                  </div>

                  <h4 className="text-sm font-bold text-gray-900 dark:text-white capitalize">
                    {step.action.replace("_", " ")}
                  </h4>

                  {/* Step configurations preview */}
                  <div className="mt-3 p-3 rounded-2xl bg-gray-50 dark:bg-gray-800/60 text-xs space-y-1.5 font-mono text-gray-600 dark:text-gray-300">
                    {step.action === "notify" && (
                      <>
                        <div className="truncate"><span className="text-gray-400">Title:</span> {String(step.configuration?.title ?? "—")}</div>
                        <div className="truncate"><span className="text-gray-400">User:</span> {String(step.configuration?.user_id ?? "—").slice(0, 8)}...</div>
                      </>
                    )}
                    {step.action === "send_email" && (
                      <>
                        <div className="truncate"><span className="text-gray-400">To:</span> {String(step.configuration?.to ?? "—")}</div>
                        <div className="truncate"><span className="text-gray-400">Subject:</span> {String(step.configuration?.subject ?? "—")}</div>
                      </>
                    )}
                    {step.action === "archive_document" && (
                      <div className="truncate"><span className="text-gray-400">Doc:</span> {String(step.configuration?.document_id ?? "—").slice(0, 8)}...</div>
                    )}
                    {step.action === "delay" && (
                      <div><span className="text-gray-400">Seconds:</span> {String(step.configuration?.seconds ?? 5)}s</div>
                    )}
                    {step.action === "approve" && (
                      <div className="truncate"><span className="text-gray-400">Approver:</span> {step.configuration?.approver_user_id ? String(step.configuration.approver_user_id).slice(0, 8) + "..." : "Any Manager"}</div>
                    )}
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between text-[11px] text-gray-400">
                  <span>Retries: {step.retry_count}</span>
                  {step.timeout && <span>Timeout: {step.timeout}s</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Execution History Table */}
        <div className="space-y-4 pt-4 border-t border-gray-200 dark:border-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-gray-900 dark:text-white">
                Execution History &amp; Audit Logs
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Track every run of this workflow with live step timings and logs.
              </p>
            </div>
            <button
              onClick={fetchExecutions}
              className="px-3 py-1.5 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-xs font-semibold text-gray-700 dark:text-gray-300 transition-all flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Refresh</span>
            </button>
          </div>

          {executions.length === 0 ? (
            <div className="p-8 border-2 border-dashed border-gray-200 dark:border-gray-800 rounded-3xl text-center">
              <p className="text-sm font-semibold text-gray-900 dark:text-white">
                No executions recorded yet
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Click &quot;Run Pipeline&quot; above to launch the first execution.
              </p>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-3xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-gray-50 dark:bg-gray-800/60 text-gray-500 dark:text-gray-400 uppercase tracking-wider font-semibold border-b border-gray-200 dark:border-gray-800">
                    <tr>
                      <th className="px-6 py-3.5">Execution ID</th>
                      <th className="px-6 py-3.5">Status</th>
                      <th className="px-6 py-3.5">Duration</th>
                      <th className="px-6 py-3.5">Started At</th>
                      <th className="px-6 py-3.5 text-right">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                    {executions.map((exec) => (
                      <tr
                        key={exec.id}
                        className="hover:bg-gray-50/80 dark:hover:bg-gray-800/40 transition-colors"
                      >
                        <td className="px-6 py-4 font-mono font-medium text-gray-900 dark:text-white">
                          {exec.id.slice(0, 8)}...
                        </td>
                        <td className="px-6 py-4">
                          <ExecutionStatusBadge status={exec.status} />
                        </td>
                        <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                          {exec.duration !== null && exec.duration !== undefined
                            ? `${exec.duration.toFixed(2)}s`
                            : "—"}
                        </td>
                        <td className="px-6 py-4 text-gray-500 dark:text-gray-400">
                          {new Date(exec.created_at).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={() => setSelectedExecution(exec)}
                            className="px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 font-semibold transition-all"
                          >
                            View Logs
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Logs Drawer / Modal */}
        {selectedExecution && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-3xl w-full max-w-2xl shadow-2xl overflow-hidden my-8">
              <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-gray-900 dark:text-white">
                      Execution Logs
                    </h3>
                    <ExecutionStatusBadge status={selectedExecution.status} size="sm" />
                  </div>
                  <p className="text-xs font-mono text-gray-500 dark:text-gray-400 mt-0.5">
                    {selectedExecution.id}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedExecution(null)}
                  className="w-8 h-8 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 flex items-center justify-center text-gray-500"
                >
                  ✕
                </button>
              </div>

              <div className="p-6 space-y-4 max-h-[calc(80vh-140px)] overflow-y-auto">
                {selectedExecution.logs?.steps && selectedExecution.logs.steps.length > 0 ? (
                  <div className="space-y-3">
                    {selectedExecution.logs.steps.map((logStep, i) => (
                      <div
                        key={i}
                        className="p-4 rounded-2xl bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700/60 space-y-2 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-gray-900 dark:text-white">
                            Step {logStep.step_number}: {logStep.action}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase ${
                              logStep.status === "completed"
                                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                                : logStep.status === "failed"
                                ? "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
                                : "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                            }`}
                          >
                            {logStep.status}
                          </span>
                        </div>

                        {logStep.duration !== undefined && (
                          <div className="text-gray-500 dark:text-gray-400">
                            Duration: {logStep.duration.toFixed(3)}s
                          </div>
                        )}

                        {logStep.error && (
                          <div className="p-2 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 font-mono">
                            {logStep.error}
                          </div>
                        )}

                        {logStep.result && (
                          <pre className="p-2 rounded-lg bg-gray-100 dark:bg-gray-900 text-gray-700 dark:text-gray-300 font-mono overflow-x-auto text-[11px]">
                            {JSON.stringify(logStep.result, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-8 text-center text-xs text-gray-500 dark:text-gray-400 font-mono bg-gray-50 dark:bg-gray-800/40 rounded-2xl">
                    No detailed step logs recorded for this execution.
                  </div>
                )}
              </div>

              <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-800 flex justify-end bg-gray-50 dark:bg-gray-900/50">
                <button
                  onClick={() => setSelectedExecution(null)}
                  className="px-5 py-2 bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 text-xs font-semibold rounded-xl transition-all"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Edit Modal */}
        <WorkflowFormModal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          onSuccess={(updated) => {
            setWorkflow(updated);
            setToastMessage(`Workflow "${updated.name}" updated successfully.`);
            setTimeout(() => setToastMessage(null), 4000);
          }}
          workflowToEdit={workflow}
        />
      </div>
    </DashboardLayout>
  );
}
