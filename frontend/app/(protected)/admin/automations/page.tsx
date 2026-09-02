"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/store/auth.store";
import {
  getAutomationRules,
  createAutomationRule,
  updateAutomationRule,
  deleteAutomationRule,
  getAutomationExecutions,
  testAutomationRule,
} from "@/services/automation.service";
import type {
  AutomationAction,
  AutomationCondition,
  AutomationExecution,
  AutomationRule,
  AutomationTestResult,
} from "@/types/automation";
import ErrorBoundary from "@/components/ui/ErrorBoundary";

function BoltIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  );
}

function PlusIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
    </svg>
  );
}

function RefreshIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

export default function AutomationsAdminPage() {
  const { user, isInitializing, isAuthenticated } = useAuthStore();
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [formName, setFormName] = useState("");
  const [formTrigger, setFormTrigger] = useState("document.created");
  const [formDescription, setFormDescription] = useState("");
  const [formConditionsStr, setFormConditionsStr] = useState('[\n  {\n    "field": "payload.confidentiality",\n    "operator": "equals",\n    "value": "restricted"\n  }\n]');
  const [formActionsStr, setFormActionsStr] = useState('[\n  {\n    "type": "send_notification",\n    "config": {\n      "title": "Restricted Document Created",\n      "message": "A restricted document has been uploaded for review."\n    }\n  }\n]');

  // Executions Modal
  const [selectedRule, setSelectedRule] = useState<AutomationRule | null>(null);
  const [executions, setExecutions] = useState<AutomationExecution[]>([]);
  const [execLoading, setExecLoading] = useState(false);

  // Test Simulation
  const [testingRule, setTestingRule] = useState<AutomationRule | null>(null);
  const [testContextStr, setTestContextStr] = useState('{\n  "payload": {\n    "confidentiality": "restricted",\n    "title": "Confidential Strategy Report"\n  }\n}');
  const [testResult, setTestResult] = useState<AutomationTestResult | null>(null);

  const role = user?.role?.toLowerCase() || "";
  const isAuthorized = ["admin", "manager"].includes(role);
  const isAdmin = role === "admin";

  const fetchRules = useCallback(async () => {
    if (!isAuthorized) return;
    setLoading(true);
    try {
      const res = await getAutomationRules(1, 50);
      setRules(res.items);
    } catch {
      // Ignored
    } finally {
      setLoading(false);
    }
  }, [isAuthorized]);

  useEffect(() => {
    if (!isInitializing && isAuthenticated && isAuthorized) {
      fetchRules();
    }
  }, [isInitializing, isAuthenticated, isAuthorized, fetchRules]);

  const handleOpenCreate = () => {
    setEditingRuleId(null);
    setFormName("");
    setFormTrigger("document.created");
    setFormDescription("");
    setFormConditionsStr('[\n  {\n    "field": "payload.confidentiality",\n    "operator": "equals",\n    "value": "restricted"\n  }\n]');
    setFormActionsStr('[\n  {\n    "type": "send_notification",\n    "config": {\n      "title": "Restricted Document Created",\n      "message": "A restricted document has been uploaded for review."\n    }\n  }\n]');
    setIsModalOpen(true);
  };

  const handleOpenEdit = (rule: AutomationRule) => {
    setEditingRuleId(rule.id);
    setFormName(rule.name);
    setFormTrigger(rule.trigger_event);
    setFormDescription(rule.description || "");
    setFormConditionsStr(JSON.stringify(rule.conditions || [], null, 2));
    setFormActionsStr(JSON.stringify(rule.actions || [], null, 2));
    setIsModalOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const conds = JSON.parse(formConditionsStr) as AutomationCondition[];
      const acts = JSON.parse(formActionsStr) as AutomationAction[];
      if (editingRuleId) {
        await updateAutomationRule(editingRuleId, {
          name: formName,
          trigger_event: formTrigger,
          conditions: conds,
          actions: acts,
          description: formDescription,
        });
      } else {
        await createAutomationRule({
          name: formName,
          trigger_event: formTrigger,
          conditions: conds,
          actions: acts,
          description: formDescription,
        });
      }
      setIsModalOpen(false);
      fetchRules();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Invalid JSON or save failed.";
      alert(msg);
    }
  };

  const handleToggleActive = async (rule: AutomationRule) => {
    try {
      await updateAutomationRule(rule.id, { is_active: !rule.is_active });
      fetchRules();
    } catch {
      alert("Failed to toggle rule status");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this automation rule?")) return;
    try {
      await deleteAutomationRule(id);
      fetchRules();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      alert(msg);
    }
  };

  const fetchExecutions = async (rule: AutomationRule) => {
    setSelectedRule(rule);
    setExecLoading(true);
    try {
      const res = await getAutomationExecutions(rule.id, 1, 20);
      setExecutions(res.items);
    } catch {
      alert("Failed to load executions");
    } finally {
      setExecLoading(false);
    }
  };

  const handleRunDryRun = async () => {
    if (!testingRule) return;
    try {
      const parsedContext = JSON.parse(testContextStr) as Record<string, unknown>;
      const res = await testAutomationRule(testingRule.id, parsedContext);
      setTestResult(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Invalid JSON context";
      alert(msg);
    }
  };

  if (!isInitializing && !isAuthorized) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-red-950/40 border border-red-800/60 rounded-xl p-6 text-center text-red-300">
          <h2 className="text-xl font-bold mb-2">Access Restricted</h2>
          <p>Automation Rule Engine is reserved for Administrators and Managers.</p>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="space-y-6 max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-900/60 p-6 rounded-2xl border border-slate-800 backdrop-blur-md">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-400">
              <BoltIcon className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Automation Rules Engine</h1>
              <p className="text-sm text-slate-400">
                Trigger autonomous actions (notifications, webhooks, workflows) when internal events occur.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchRules}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-xl border border-slate-700 transition"
            >
              <RefreshIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            {isAdmin && (
              <button
                onClick={handleOpenCreate}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-xl shadow-lg shadow-amber-600/30 transition"
              >
                <PlusIcon className="w-4 h-4" />
                Create Rule
              </button>
            )}
          </div>
        </div>

        {/* Rules Table */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden backdrop-blur-sm shadow-xl">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/80 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="px-6 py-4">Rule Name</th>
                <th className="px-6 py-4">Trigger Event</th>
                <th className="px-6 py-4">Conditions</th>
                <th className="px-6 py-4">Actions</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-500">
                    Loading automation rules...
                  </td>
                </tr>
              ) : rules.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-500">
                    No automation rules defined. Click &quot;Create Rule&quot; to build an event workflow.
                  </td>
                </tr>
              ) : (
                rules.map((rule) => (
                  <tr key={rule.id} className="hover:bg-slate-800/30 transition">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-white">{rule.name}</div>
                      {rule.description && <div className="text-xs text-slate-400">{rule.description}</div>}
                    </td>
                    <td className="px-6 py-4">
                      <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/20">
                        {rule.trigger_event}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-300">
                      {rule.conditions?.length ? (
                        <span>{rule.conditions.length} condition(s)</span>
                      ) : (
                        <span className="text-slate-500">Unconditional</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-300">
                      <div className="flex flex-wrap gap-1">
                        {(rule.actions || []).map((act, i) => (
                          <span
                            key={i}
                            className="px-2 py-0.5 rounded bg-slate-800 text-cyan-300 text-xs font-mono"
                          >
                            {act.type}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => isAdmin && handleToggleActive(rule)}
                        disabled={!isAdmin}
                        className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                          rule.is_active
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-slate-800 text-slate-400 border border-slate-700"
                        }`}
                      >
                        {rule.is_active ? "Active" : "Disabled"}
                      </button>
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => {
                          setTestingRule(rule);
                          setTestResult(null);
                        }}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition"
                      >
                        Dry Run
                      </button>
                      <button
                        onClick={() => fetchExecutions(rule)}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-amber-400 text-xs font-medium rounded-lg transition"
                      >
                        Logs
                      </button>
                      {isAdmin && (
                        <>
                          <button
                            onClick={() => handleOpenEdit(rule)}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDelete(rule.id)}
                            className="px-2.5 py-1 bg-red-950/40 hover:bg-red-900/60 text-red-400 border border-red-800/50 text-xs font-medium rounded-lg transition"
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Create/Edit Modal */}
        {isModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
              <h2 className="text-xl font-bold text-white">
                {editingRuleId ? "Edit Automation Rule" : "Create Automation Rule"}
              </h2>
              <form onSubmit={handleSave} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Rule Name</label>
                  <input
                    type="text"
                    required
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Notify on Confidential Document Creation"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Trigger Event</label>
                  <input
                    type="text"
                    required
                    value={formTrigger}
                    onChange={(e) => setFormTrigger(e.target.value)}
                    placeholder="e.g. document.created, security.alert, report.completed, *"
                    className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-amber-300 focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Conditions (JSON Array)</label>
                  <textarea
                    rows={4}
                    value={formConditionsStr}
                    onChange={(e) => setFormConditionsStr(e.target.value)}
                    className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl p-3 text-cyan-300 focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Actions (JSON Array)</label>
                  <textarea
                    rows={4}
                    value={formActionsStr}
                    onChange={(e) => setFormActionsStr(e.target.value)}
                    className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl p-3 text-emerald-400 focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-xl transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-xl shadow-md transition"
                  >
                    Save Rule
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Dry Run / Test Modal */}
        {testingRule && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                <h3 className="text-lg font-bold text-white">Dry-Run Rule: {testingRule.name}</h3>
                <button
                  onClick={() => {
                    setTestingRule(null);
                    setTestResult(null);
                  }}
                  className="text-slate-400 hover:text-white text-sm font-bold"
                >
                  ✕
                </button>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Synthetic Event Context (JSON)</label>
                <textarea
                  rows={5}
                  value={testContextStr}
                  onChange={(e) => setTestContextStr(e.target.value)}
                  className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl p-3 text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handleRunDryRun}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold rounded-xl"
                >
                  Evaluate Rule Conditions
                </button>
              </div>

              {testResult && (
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs font-mono">
                  <div className="flex justify-between">
                    <span>Conditions Met:</span>
                    <span className={testResult.conditions_met ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                      {testResult.conditions_met ? "TRUE (MATCHED)" : "FALSE (SKIPPED)"}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Actions to trigger:</span>
                    <span>{testResult.actions_to_execute} action(s)</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Evaluation duration:</span>
                    <span>{testResult.duration_ms}ms</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Executions Modal */}
        {selectedRule && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                <div>
                  <h3 className="text-lg font-bold text-white">Execution Logs: {selectedRule.name}</h3>
                  <p className="text-xs text-slate-400">Trigger: {selectedRule.trigger_event}</p>
                </div>
                <button
                  onClick={() => setSelectedRule(null)}
                  className="text-slate-400 hover:text-white text-sm font-bold px-2 py-1"
                >
                  ✕
                </button>
              </div>

              <div className="overflow-y-auto flex-1 space-y-3">
                {execLoading ? (
                  <div className="text-center py-8 text-slate-500">Loading executions...</div>
                ) : executions.length === 0 ? (
                  <div className="text-center py-8 text-slate-500">No executions recorded yet.</div>
                ) : (
                  executions.map((item) => (
                    <div
                      key={item.id}
                      className="bg-slate-950 border border-slate-800/80 rounded-xl p-4 text-xs font-mono space-y-2"
                    >
                      <div className="flex justify-between items-center">
                        <span className="font-semibold text-white">{item.event_type}</span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                            item.status === "success"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          }`}
                        >
                          {item.status.toUpperCase()}
                        </span>
                      </div>
                      <div className="text-slate-400 flex justify-between">
                        <span>Duration: {item.execution_time_ms ?? 0}ms</span>
                        <span>{new Date(item.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
