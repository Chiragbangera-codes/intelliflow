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
    <DashboardLayout>
      {/* ── Page header ── */}
      <div style={{ marginBottom: 40 }}>
        <p className="eyebrow" style={{ color: "var(--accent)", marginBottom: 12 }}>Automation</p>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <h1
            style={{
              fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
              fontSize: "clamp(1.75rem, 3vw, 2.5rem)",
              fontWeight: 800,
              letterSpacing: "-0.04em",
              color: "#f8fafc",
              lineHeight: 1.1,
              margin: 0,
            }}
          >
            Workflows &
            <br />
            <span style={{ color: "var(--ink-40)" }}>automated pipelines.</span>
          </h1>
          {canManage && (
            <button
              onClick={() => { setWorkflowToEdit(null); setIsCreateModalOpen(true); }}
              className="btn btn-primary"
              style={{ flexShrink: 0 }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Create Workflow
            </button>
          )}
        </div>
      </div>

      {/* ── Toast ── */}
      {toastMessage && (
        <div style={{ marginBottom: 20, padding: "11px 16px", background: "rgb(22 163 74 / 0.08)", border: "1px solid rgb(22 163 74 / 0.2)", borderRadius: 8, fontSize: 13, color: "#4ade80", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>{toastMessage}</span>
          <button onClick={() => setToastMessage(null)} style={{ background: "none", border: "none", color: "#4ade80", fontSize: 12, cursor: "pointer" }}>Dismiss</button>
        </div>
      )}

      {/* ── Metric strip ── */}
      <div style={{ display: "flex", border: "1px solid var(--ink-70)", borderRadius: 12, overflow: "hidden", marginBottom: 32 }}>
        {[
          { label: "Total Workflows", value: workflows.length },
          { label: "Active Pipelines", value: activeCount },
          { label: "Inactive", value: workflows.length - activeCount },
          { label: "Automation Engine", value: "Celery + Redis" },
        ].map((item, i, arr) => (
          <div key={item.label} style={{ flex: 1, padding: "20px 24px", borderRight: i < arr.length - 1 ? "1px solid var(--ink-70)" : "none" }}>
            <span style={{ display: "block", fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))", fontSize: typeof item.value === "number" ? "clamp(1.5rem, 2.5vw, 2rem)" : 14, fontWeight: 800, letterSpacing: "-0.03em", color: "#f1f5f9", lineHeight: 1, marginBottom: 6 }}>
              {item.value}
            </span>
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--ink-40)" }}>
              {item.label}
            </span>
          </div>
        ))}
      </div>

      {/* ── Filter bar ── */}
      <div style={{ display: "flex", gap: 10, marginBottom: 24, flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 240px" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ink-60)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search workflows..."
            className="input"
            style={{ paddingLeft: 36 }}
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as "all" | "active" | "inactive")}
          className="input"
          style={{ flex: "0 1 160px" }}
        >
          <option value="all">All Status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        {error && (
          <div style={{ flex: "1 1 100%", padding: "10px 14px", background: "rgb(220 38 38 / 0.08)", border: "1px solid rgb(220 38 38 / 0.2)", borderRadius: 8, fontSize: 13, color: "#f87171" }}>
            {error}
          </div>
        )}
      </div>

      {/* ── Workflows ── */}
      {loading ? (
        <LoadingSpinner size="lg" message="Loading workflows..." />
      ) : filteredWorkflows.length === 0 ? (
        <div style={{ padding: "64px 32px", textAlign: "center", background: "var(--ink-90)", border: "1px solid var(--ink-70)", borderRadius: 12 }}>
          <p style={{ fontFamily: "var(--font-jakarta, sans-serif)", fontSize: 16, fontWeight: 700, color: "#f1f5f9", marginBottom: 8 }}>No workflows found</p>
          <p style={{ fontSize: 13, color: "var(--ink-40)", marginBottom: 24 }}>
            {searchQuery ? "Adjust your search." : "Create your first automated pipeline."}
          </p>
          {canManage && (
            <button onClick={() => { setWorkflowToEdit(null); setIsCreateModalOpen(true); }} className="btn btn-primary btn-sm">
              Create Workflow
            </button>
          )}
        </div>
      ) : (
        <div
          style={{
            background: "var(--ink-90)",
            border: "1px solid var(--ink-70)",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          {filteredWorkflows.map((workflow, idx) => (
            <div
              key={workflow.id}
              onClick={() => router.push(`/workflows/${workflow.id}`)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                padding: "18px 20px",
                borderBottom: idx < filteredWorkflows.length - 1 ? "1px solid var(--ink-80)" : "none",
                cursor: "pointer",
                transition: "background 0.1s",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "rgb(255 255 255 / 0.02)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              {/* Status dot */}
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: workflow.is_active ? "#4ade80" : "var(--ink-60)", flexShrink: 0 }} />

              {/* Name + desc */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0", letterSpacing: "-0.01em", margin: "0 0 3px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {workflow.name}
                </p>
                <p style={{ fontSize: 12, color: "var(--ink-40)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {workflow.description || "No description"} &nbsp;·&nbsp; {workflow.steps.length} step{workflow.steps.length !== 1 ? "s" : ""} &nbsp;·&nbsp; v{workflow.version}
                </p>
              </div>

              {/* Steps pills */}
              <div style={{ display: "flex", gap: 4, flexWrap: "nowrap", overflow: "hidden" }}>
                {workflow.steps.slice(0, 4).map((step) => {
                  const stepMap: Record<string, string> = {
                    notify: "Notify", send_email: "Email", archive_document: "Archive",
                    approve: "Approve", delay: "Delay",
                  };
                  return (
                    <span key={step.id} style={{ fontSize: 10, fontWeight: 600, padding: "2px 8px", background: "var(--ink-80)", border: "1px solid var(--ink-70)", borderRadius: 4, color: "var(--ink-40)", letterSpacing: "0.03em", textTransform: "uppercase", whiteSpace: "nowrap" }}>
                      {stepMap[step.action] || step.action}
                    </span>
                  );
                })}
                {workflow.steps.length > 4 && (
                  <span style={{ fontSize: 10, color: "var(--ink-60)", padding: "2px 4px" }}>+{workflow.steps.length - 4}</span>
                )}
              </div>

              {/* Status */}
              <span className={`badge ${workflow.is_active ? "badge-active" : "badge-draft"}`} style={{ flexShrink: 0 }}>
                {workflow.is_active ? "Active" : "Inactive"}
              </span>

              {/* Actions */}
              <div style={{ display: "flex", gap: 4, flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
                {canManage && (
                  <button
                    disabled={!workflow.is_active || runningId === workflow.id}
                    onClick={(e) => handleTrigger(e, workflow)}
                    className="btn btn-primary btn-sm"
                    style={{ opacity: (!workflow.is_active || runningId === workflow.id) ? 0.4 : 1 }}
                    title="Run workflow"
                  >
                    {runningId === workflow.id ? (
                      <span style={{ width: 10, height: 10, border: "2px solid rgb(255 255 255 / 0.3)", borderTopColor: "white", borderRadius: "50%", animation: "spin 0.7s linear infinite", display: "inline-block" }} />
                    ) : "Run"}
                  </button>
                )}
                {canManage && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setWorkflowToEdit(workflow); setIsCreateModalOpen(true); }}
                    className="btn btn-ghost btn-sm"
                    title="Edit"
                  >
                    Edit
                  </button>
                )}
                {isAdmin && (
                  <button
                    onClick={(e) => handleDelete(e, workflow)}
                    className="btn btn-sm"
                    style={{ background: "transparent", border: "1px solid transparent", color: "#f87171", cursor: "pointer", fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 6, transition: "all 0.1s" }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "rgb(220 38 38 / 0.1)"; e.currentTarget.style.borderColor = "rgb(220 38 38 / 0.2)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "transparent"; }}
                    title="Delete"
                  >
                    Delete
                  </button>
                )}
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
            setToastMessage(`Workflow "${saved.name}" updated.`);
          } else {
            setWorkflows((prev) => [saved, ...prev]);
            setToastMessage(`Workflow "${saved.name}" created.`);
          }
          setTimeout(() => setToastMessage(null), 5000);
        }}
        workflowToEdit={workflowToEdit}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </DashboardLayout>
  );
}
