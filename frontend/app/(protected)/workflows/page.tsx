"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useAuthStore } from "@/store/auth.store";
import type { Workflow } from "@/types";
import {
  deleteWorkflow,
  listWorkflows,
  triggerWorkflow,
} from "@/services/workflow.service";
import { WorkflowFormModal } from "@/features/workflows";

export default function WorkflowsPage() {
  const router = useRouter();
  const { user } = useAuthStore();

  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [workflowToEdit, setWorkflowToEdit] = useState<Workflow | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const canManage = user?.role === "admin" || user?.role === "manager";
  const isAdmin = user?.role === "admin";

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await listWorkflows(1, 100);
      if (res.success && res.data) {
        setWorkflows(res.data);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load workflows";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleTrigger = async (e: React.MouseEvent, workflow: Workflow) => {
    e.stopPropagation();
    try {
      setRunningId(workflow.id);
      const res = await triggerWorkflow(workflow.id);
      if (res.success && res.data) {
        setToastMessage(`Workflow "${workflow.name}" triggered! Execution ID: ${res.data.execution_id.slice(0, 8)}...`);
        setTimeout(() => setToastMessage(null), 5000);
        router.push(`/workflows/${workflow.id}`);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to trigger workflow";
      setError(msg);
    } finally {
      setRunningId(null);
    }
  };

  const handleDelete = async (e: React.MouseEvent, workflow: Workflow) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to delete workflow "${workflow.name}"?`)) {
      return;
    }
    try {
      const res = await deleteWorkflow(workflow.id);
      if (res.success) {
        setWorkflows((prev) => prev.filter((w) => w.id !== workflow.id));
        setToastMessage(`Workflow "${workflow.name}" deleted successfully.`);
        setTimeout(() => setToastMessage(null), 4000);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete workflow";
      setError(msg);
    }
  };

  const filteredWorkflows = workflows.filter((w) => {
    const matchesSearch =
      w.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (w.description && w.description.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "active" && w.is_active) ||
      (statusFilter === "inactive" && !w.is_active);
    return matchesSearch && matchesStatus;
  });

  const activeCount = workflows.filter((w) => w.is_active).length;

  return (
    <DashboardLayout
      title="Automated Workflows"
      description="Design, execute, and monitor multi-step automated process pipelines."
    >
      <div className="space-y-6">
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

        {/* Top Controls & Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-5 rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-blue-50 dark:bg-blue-950/50 flex items-center justify-center text-blue-600 dark:text-blue-400 font-bold text-xl">
              ⚡
            </div>
            <div>
              <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">Total Workflows</span>
              <h4 className="text-2xl font-bold text-gray-900 dark:text-white">{workflows.length}</h4>
            </div>
          </div>

          <div className="p-5 rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-50 dark:bg-emerald-950/50 flex items-center justify-center text-emerald-600 dark:text-emerald-400 font-bold text-xl">
              🟢
            </div>
            <div>
              <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">Active Pipelines</span>
              <h4 className="text-2xl font-bold text-gray-900 dark:text-white">{activeCount}</h4>
            </div>
          </div>

          <div className="p-5 rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm flex items-center justify-between">
            <div>
              <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">Automation Engine</span>
              <p className="text-xs text-gray-700 dark:text-gray-300 font-semibold mt-1">Celery + Redis Broker</p>
            </div>
            <span className="px-2.5 py-1 rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 text-[10px] font-bold uppercase tracking-wider">
              Operational
            </span>
          </div>
        </div>

        {/* Filter bar & Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm">
          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
            <div className="relative flex-1 sm:w-72">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
                🔍
              </span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search workflows by name..."
                className="w-full pl-9 pr-4 py-2 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
              />
            </div>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as "all" | "active" | "inactive")}
              className="px-3 py-2 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active Only</option>
              <option value="inactive">Inactive Only</option>
            </select>
          </div>

          {canManage && (
            <button
              onClick={() => {
                setWorkflowToEdit(null);
                setIsCreateModalOpen(true);
              }}
              className="w-full sm:w-auto px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-md shadow-blue-600/20 hover:shadow-lg hover:shadow-blue-600/30 transition-all flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Create Workflow</span>
            </button>
          )}
        </div>

        {/* Workflow List Table / Grid */}
        {loading ? (
          <LoadingSpinner message="Loading workflow registry..." />
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
            {error}
          </div>
        ) : filteredWorkflows.length === 0 ? (
          <div className="p-12 border-2 border-dashed border-gray-300 dark:border-gray-800 rounded-3xl text-center bg-white/50 dark:bg-gray-900/50">
            <div className="w-16 h-16 rounded-2xl bg-blue-50 dark:bg-blue-950/50 flex items-center justify-center mx-auto mb-4 text-3xl">
              ⚡
            </div>
            <h3 className="text-base font-bold text-gray-900 dark:text-white">No workflows found</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-sm mx-auto">
              {searchQuery
                ? "No workflows match your search filters."
                : "Create automated pipelines to eliminate repetitive document and approval tasks."}
            </p>
            {canManage && (
              <button
                onClick={() => {
                  setWorkflowToEdit(null);
                  setIsCreateModalOpen(true);
                }}
                className="mt-4 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-md shadow-blue-600/20 transition-all inline-flex items-center gap-2"
              >
                <span>Create First Workflow</span>
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredWorkflows.map((workflow) => (
              <div
                key={workflow.id}
                onClick={() => router.push(`/workflows/${workflow.id}`)}
                className="p-6 rounded-3xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm hover:shadow-xl hover:border-blue-500 dark:hover:border-blue-500 transition-all cursor-pointer flex flex-col justify-between group relative overflow-hidden"
              >
                {/* Status indicator bar */}
                <div
                  className={`absolute top-0 left-0 right-0 h-1.5 ${
                    workflow.is_active
                      ? "bg-gradient-to-r from-blue-500 to-indigo-600"
                      : "bg-gray-300 dark:bg-gray-700"
                  }`}
                />

                <div>
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <h3 className="text-base font-bold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-1">
                      {workflow.name}
                    </h3>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider shrink-0 ${
                        workflow.is_active
                          ? "bg-emerald-100 dark:bg-emerald-950/70 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                          : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                      }`}
                    >
                      {workflow.is_active ? "Active" : "Disabled"}
                    </span>
                  </div>

                  <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 min-h-[32px]">
                    {workflow.description || "No description provided."}
                  </p>

                  {/* Steps preview chips */}
                  <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800/80">
                    <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider block mb-2">
                      Pipeline Sequence ({workflow.steps.length} Steps)
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {workflow.steps.map((step) => {
                        const stepLabels: Record<string, { label: string; bg: string }> = {
                          notify: { label: "🔔 Notify", bg: "bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300" },
                          send_email: { label: "✉️ Email", bg: "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300" },
                          archive_document: { label: "📁 Archive", bg: "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300" },
                          approve: { label: "🛡️ Approve", bg: "bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300" },
                          delay: { label: "⏱️ Delay", bg: "bg-cyan-50 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-300" },
                        };
                        const info = stepLabels[step.action] || { label: step.action, bg: "bg-gray-100 text-gray-700" };
                        return (
                          <span
                            key={step.id}
                            className={`px-2 py-0.5 rounded-lg text-[11px] font-medium ${info.bg}`}
                          >
                            {step.step_number}. {info.label}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Footer Controls */}
                <div className="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-2">
                  <div className="text-[11px] text-gray-400 truncate">
                    By {workflow.creator_name || "System"} • v{workflow.version}
                  </div>

                  <div className="flex items-center gap-1.5">
                    {canManage && (
                      <button
                        type="button"
                        disabled={!workflow.is_active || runningId === workflow.id}
                        onClick={(e) => handleTrigger(e, workflow)}
                        className="px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-800 text-white text-xs font-bold shadow-sm hover:shadow-md transition-all flex items-center gap-1.5 disabled:cursor-not-allowed"
                        title={workflow.is_active ? "Run Workflow" : "Workflow is inactive"}
                      >
                        {runningId === workflow.id ? (
                          <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        )}
                        <span>Run</span>
                      </button>
                    )}

                    {canManage && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setWorkflowToEdit(workflow);
                          setIsCreateModalOpen(true);
                        }}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-all"
                        title="Edit workflow"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                    )}

                    {isAdmin && (
                      <button
                        type="button"
                        onClick={(e) => handleDelete(e, workflow)}
                        className="p-1.5 rounded-lg text-rose-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-all"
                        title="Delete workflow"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create / Edit Modal */}
        <WorkflowFormModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={(saved) => {
            if (workflowToEdit) {
              setWorkflows((prev) => prev.map((w) => (w.id === saved.id ? saved : w)));
              setToastMessage(`Workflow "${saved.name}" updated successfully.`);
            } else {
              setWorkflows((prev) => [saved, ...prev]);
              setToastMessage(`Workflow "${saved.name}" created successfully.`);
            }
            setTimeout(() => setToastMessage(null), 5000);
          }}
          workflowToEdit={workflowToEdit}
        />
      </div>
    </DashboardLayout>
  );
}
