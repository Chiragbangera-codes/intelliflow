"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/store/auth.store";
import {
  getIntegrations,
  createIntegration,
  updateIntegration,
  deleteIntegration,
  testIntegration,
} from "@/services/integration.service";
import type {
  Integration,
  IntegrationProvider,
} from "@/types/integration";
import ErrorBoundary from "@/components/ui/ErrorBoundary";

function GlobeIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
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

function CheckCircleIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
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

export default function IntegrationsAdminPage() {
  const { user, isInitializing, isAuthenticated } = useAuthStore();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState("");
  const [formProvider, setFormProvider] = useState<IntegrationProvider>("slack");
  const [formDescription, setFormDescription] = useState("");
  const [formConfigStr, setFormConfigStr] = useState('{\n  "webhook_url": "https://hooks.slack.com/services/..."\n}');
  const [formCredsStr, setFormCredsStr] = useState('{\n  "api_key": "xoxb-..."\n}');
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null);

  const role = user?.role?.toLowerCase() || "";
  const isAuthorized = ["admin", "manager"].includes(role);
  const isAdmin = role === "admin";

  const fetchIntegrations = useCallback(async () => {
    if (!isAuthorized) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getIntegrations(1, 50);
      setIntegrations(res.items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load integrations";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [isAuthorized]);

  useEffect(() => {
    if (!isInitializing && isAuthenticated && isAuthorized) {
      fetchIntegrations();
    }
  }, [isInitializing, isAuthenticated, isAuthorized, fetchIntegrations]);

  if (!isInitializing && !isAuthorized) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-red-950/40 border border-red-800/60 rounded-xl p-6 text-center text-red-300">
          <h2 className="text-xl font-bold mb-2">Access Restricted</h2>
          <p>Integration management is reserved for Administrators and Managers.</p>
        </div>
      </div>
    );
  }

  const handleOpenCreate = () => {
    setEditingId(null);
    setFormName("");
    setFormProvider("slack");
    setFormDescription("");
    setFormConfigStr('{\n  "webhook_url": "https://hooks.slack.com/services/..."\n}');
    setFormCredsStr("");
    setIsModalOpen(true);
  };

  const handleOpenEdit = (integ: Integration) => {
    setEditingId(integ.id);
    setFormName(integ.name);
    setFormProvider(integ.provider);
    setFormDescription(integ.description || "");
    setFormConfigStr(JSON.stringify(integ.configuration || {}, null, 2));
    setFormCredsStr("");
    setIsModalOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const configObj = formConfigStr.trim() ? JSON.parse(formConfigStr) : {};
      const credsObj = formCredsStr.trim() ? JSON.parse(formCredsStr) : undefined;

      if (editingId) {
        await updateIntegration(editingId, {
          name: formName,
          description: formDescription,
          configuration: configObj,
          credentials: credsObj,
        });
      } else {
        await createIntegration({
          name: formName,
          provider: formProvider,
          description: formDescription,
          configuration: configObj,
          credentials: credsObj,
        });
      }
      setIsModalOpen(false);
      fetchIntegrations();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Invalid JSON or save failed.";
      alert(msg);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this integration?")) return;
    try {
      await deleteIntegration(id);
      fetchIntegrations();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      alert(msg);
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    setTestResult(null);
    try {
      const res = await testIntegration(id);
      setTestResult({
        id,
        success: res.success,
        message: res.success ? (res.message || "Connection verified successfully!") : (res.error || "Connection failed"),
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Test connection failed";
      setTestResult({
        id,
        success: false,
        message: msg,
      });
    } finally {
      setTestingId(null);
    }
  };

  return (
    <ErrorBoundary>
      <div className="space-y-6 max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-900/60 p-6 rounded-2xl border border-slate-800 backdrop-blur-md">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-400">
              <GlobeIcon className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Enterprise Integrations</h1>
              <p className="text-sm text-slate-400">
                Connect IntelliFlow with external chat, ticketing, notifications, and web service endpoints.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchIntegrations}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-xl border border-slate-700 transition"
            >
              <RefreshIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            {isAdmin && (
              <button
                onClick={handleOpenCreate}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl shadow-lg shadow-indigo-600/30 transition"
              >
                <PlusIcon className="w-4 h-4" />
                Add Integration
              </button>
            )}
          </div>
        </div>

        {/* Test Result Banner */}
        {testResult && (
          <div
            className={`p-4 rounded-xl border flex items-center justify-between ${
              testResult.success
                ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                : "bg-rose-950/40 border-rose-800/60 text-rose-300"
            }`}
          >
            <div className="flex items-center gap-3">
              <CheckCircleIcon className="w-5 h-5" />
              <span>{testResult.message}</span>
            </div>
            <button
              onClick={() => setTestResult(null)}
              className="text-xs underline hover:opacity-80"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Integration Grid */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-48 bg-slate-900/40 rounded-2xl border border-slate-800/60 animate-pulse p-6" />
            ))}
          </div>
        ) : error ? (
          <div className="bg-red-950/30 border border-red-800/40 rounded-2xl p-6 text-red-300">
            {error}
          </div>
        ) : integrations.length === 0 ? (
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-12 text-center">
            <GlobeIcon className="w-12 h-12 text-slate-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-white mb-1">No integrations configured</h3>
            <p className="text-sm text-slate-400 max-w-md mx-auto mb-6">
              Connect third-party platforms like Slack, Microsoft Teams, SMTP email, or custom Webhook receivers.
            </p>
            {isAdmin && (
              <button
                onClick={handleOpenCreate}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl transition"
              >
                Configure First Integration
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {integrations.map((integ) => (
              <div
                key={integ.id}
                className="bg-slate-900/70 border border-slate-800 hover:border-slate-700 rounded-2xl p-6 flex flex-col justify-between backdrop-blur-sm transition shadow-lg"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <span className="px-2.5 py-1 text-xs font-semibold rounded-full uppercase tracking-wider bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                      {integ.provider}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full ${
                        integ.status === "active"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${integ.status === "active" ? "bg-emerald-400" : "bg-amber-400"}`} />
                      {integ.status}
                    </span>
                  </div>
                  <h3 className="text-lg font-semibold text-white mb-1">{integ.name}</h3>
                  {integ.description && (
                    <p className="text-xs text-slate-400 mb-4 line-clamp-2">{integ.description}</p>
                  )}
                  <div className="space-y-1.5 text-xs text-slate-400 border-t border-slate-800/80 pt-3">
                    <div className="flex justify-between">
                      <span>Credentials:</span>
                      <span className={integ.has_credentials ? "text-emerald-400 font-medium" : "text-slate-500"}>
                        {integ.has_credentials ? "Encrypted (AES-GCM)" : "None"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Last Activity:</span>
                      <span>{integ.last_synced_at ? new Date(integ.last_synced_at).toLocaleString() : "Never"}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-2 border-t border-slate-800/80 pt-4 mt-4">
                  <button
                    onClick={() => handleTest(integ.id)}
                    disabled={testingId === integ.id}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition disabled:opacity-50"
                  >
                    {testingId === integ.id ? "Testing..." : "Test Link"}
                  </button>
                  {isAdmin && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleOpenEdit(integ)}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(integ.id)}
                        className="px-3 py-1.5 bg-red-950/40 hover:bg-red-900/60 text-red-400 border border-red-800/50 text-xs font-medium rounded-lg transition"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Modal for Create/Edit */}
        {isModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
              <h2 className="text-xl font-bold text-white">
                {editingId ? "Edit Integration" : "Configure New Integration"}
              </h2>
              <form onSubmit={handleSave} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Integration Name</label>
                  <input
                    type="text"
                    required
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Engineering Alerts Channel"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>

                {!editingId && (
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Provider Type</label>
                    <select
                      value={formProvider}
                      onChange={(e) => setFormProvider(e.target.value as IntegrationProvider)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                    >
                      <option value="slack">Slack (Incoming Webhook)</option>
                      <option value="msteams">Microsoft Teams (MessageCard)</option>
                      <option value="email">Email (SMTP)</option>
                      <option value="webhook">Generic Webhook</option>
                      <option value="generic_http">Generic HTTP / REST</option>
                    </select>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Description (Optional)</label>
                  <input
                    type="text"
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    placeholder="Operational channel for system alerts"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Configuration (JSON)</label>
                  <textarea
                    rows={4}
                    value={formConfigStr}
                    onChange={(e) => setFormConfigStr(e.target.value)}
                    className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl p-3 text-emerald-400 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Credentials (JSON - Encrypted at Rest, Never Exposed)
                  </label>
                  <textarea
                    rows={3}
                    value={formCredsStr}
                    onChange={(e) => setFormCredsStr(e.target.value)}
                    placeholder='{"api_key": "secret-value"}'
                    className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl p-3 text-amber-400 focus:outline-none focus:border-indigo-500"
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
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl shadow-md transition"
                  >
                    Save Integration
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
