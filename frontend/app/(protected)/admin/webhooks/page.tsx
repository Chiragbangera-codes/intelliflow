"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/store/auth.store";
import {
  getWebhooks,
  createWebhook,
  deleteWebhook,
  testWebhook,
  getWebhookDeliveries,
} from "@/services/webhook.service";
import type {
  Webhook,
  WebhookDelivery,
} from "@/types/webhook";
import ErrorBoundary from "@/components/ui/ErrorBoundary";

function WebhookIcon({ className = "w-5 h-5" }: { className?: string }) {
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

export default function WebhooksAdminPage() {
  const { user, isInitializing, isAuthenticated } = useAuthStore();
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [formName, setFormName] = useState("");
  const [formUrl, setFormUrl] = useState("");
  const [formEventsStr, setFormEventsStr] = useState("*");
  const [formDescription, setFormDescription] = useState("");
  const [newSecretReveal, setNewSecretReveal] = useState<string | null>(null);

  // Delivery History State
  const [selectedWebhook, setSelectedWebhook] = useState<Webhook | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);

  // Testing
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null);

  const role = user?.role?.toLowerCase() || "";
  const isAuthorized = ["admin", "manager"].includes(role);
  const isAdmin = role === "admin";

  const fetchWebhooks = useCallback(async () => {
    if (!isAuthorized) return;
    setLoading(true);
    try {
      const res = await getWebhooks(1, 50);
      setWebhooks(res.items);
    } catch {
      // Ignored
    } finally {
      setLoading(false);
    }
  }, [isAuthorized]);

  useEffect(() => {
    if (!isInitializing && isAuthenticated && isAuthorized) {
      fetchWebhooks();
    }
  }, [isInitializing, isAuthenticated, isAuthorized, fetchWebhooks]);

  const fetchDeliveries = async (wh: Webhook) => {
    setSelectedWebhook(wh);
    setDeliveriesLoading(true);
    try {
      const res = await getWebhookDeliveries(wh.id, 1, 20);
      setDeliveries(res.items);
    } catch {
      alert("Failed to load delivery history");
    } finally {
      setDeliveriesLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const eventsList = formEventsStr.split(",").map((s) => s.trim()).filter(Boolean);
      const created = await createWebhook({
        name: formName,
        url: formUrl,
        subscribed_events: eventsList.length ? eventsList : ["*"],
        description: formDescription,
      });
      setIsCreateOpen(false);
      setNewSecretReveal(created.plaintext_secret || null);
      fetchWebhooks();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create webhook.";
      alert(msg);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this webhook endpoint and its delivery logs?")) return;
    try {
      await deleteWebhook(id);
      fetchWebhooks();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      alert(msg);
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    setTestResult(null);
    try {
      const res = await testWebhook(id);
      const isSuccess = res.status === "success";
      setTestResult({
        id,
        success: isSuccess,
        message: isSuccess
          ? `Ping dispatched successfully (HTTP ${res.response_status_code}, ${res.duration_ms}ms).`
          : `Delivery failed: ${res.error_message || "HTTP " + res.response_status_code}`,
      });
      fetchWebhooks();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Test webhook failed";
      setTestResult({
        id,
        success: false,
        message: msg,
      });
    } finally {
      setTestingId(null);
    }
  };

  if (!isInitializing && !isAuthorized) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-red-950/40 border border-red-800/60 rounded-xl p-6 text-center text-red-300">
          <h2 className="text-xl font-bold mb-2">Access Restricted</h2>
          <p>Webhook management is reserved for Administrators and Managers.</p>
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
            <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded-xl text-cyan-400">
              <WebhookIcon className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Enterprise Webhooks</h1>
              <p className="text-sm text-slate-400">
                Deliver HMAC-SHA256 signed event notifications with strict SSRF filtering and retry logging.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchWebhooks}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-xl border border-slate-700 transition"
            >
              <RefreshIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            {isAdmin && (
              <button
                onClick={() => setIsCreateOpen(true)}
                className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium rounded-xl shadow-lg shadow-cyan-600/30 transition"
              >
                <PlusIcon className="w-4 h-4" />
                Register Webhook
              </button>
            )}
          </div>
        </div>

        {/* Secret Reveal Banner */}
        {newSecretReveal && (
          <div className="p-5 rounded-2xl bg-amber-950/50 border border-amber-800/80 text-amber-200 space-y-2">
            <h4 className="font-bold text-sm text-amber-300">New Webhook Signing Secret (Copy Now)</h4>
            <p className="text-xs text-amber-300/80">
              This HMAC secret is used to sign payloads in the <code className="bg-slate-950 px-1 py-0.5 rounded text-amber-200">X-IntelliFlow-Signature</code> header. It will never be shown in plaintext again.
            </p>
            <div className="flex items-center gap-3 pt-1">
              <input
                type="text"
                readOnly
                value={newSecretReveal}
                className="w-full font-mono text-xs bg-slate-950 border border-amber-700/50 rounded-lg p-2.5 text-amber-300 select-all"
              />
              <button
                onClick={() => setNewSecretReveal(null)}
                className="px-3 py-2 bg-amber-800/80 hover:bg-amber-700 text-xs font-semibold rounded-lg text-white"
              >
                Done
              </button>
            </div>
          </div>
        )}

        {/* Test Result Banner */}
        {testResult && (
          <div
            className={`p-4 rounded-xl border flex items-center justify-between ${
              testResult.success
                ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                : "bg-rose-950/40 border-rose-800/60 text-rose-300"
            }`}
          >
            <span>{testResult.message}</span>
            <button
              onClick={() => setTestResult(null)}
              className="text-xs underline hover:opacity-80 ml-4"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Webhooks Table */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden backdrop-blur-sm shadow-xl">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/80 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="px-6 py-4">Name & Description</th>
                <th className="px-6 py-4">Destination Endpoint</th>
                <th className="px-6 py-4">Subscribed Events</th>
                <th className="px-6 py-4">Signing Secret</th>
                <th className="px-6 py-4">Last Delivery</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-500">
                    Loading webhook subscribers...
                  </td>
                </tr>
              ) : webhooks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-500">
                    No webhooks registered. Click &quot;Register Webhook&quot; to add an endpoint.
                  </td>
                </tr>
              ) : (
                webhooks.map((wh) => (
                  <tr key={wh.id} className="hover:bg-slate-800/30 transition">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-white">{wh.name}</div>
                      {wh.description && <div className="text-xs text-slate-400">{wh.description}</div>}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-cyan-400 max-w-xs truncate">
                      {wh.url}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {(wh.subscribed_events || ["*"]).map((ev, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 text-xs rounded-md bg-slate-800 border border-slate-700 text-slate-300 font-mono"
                          >
                            {ev}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-slate-400">
                      {wh.masked_secret}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-400">
                      {wh.last_delivery_at ? new Date(wh.last_delivery_at).toLocaleString() : "Never"}
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => handleTest(wh.id)}
                        disabled={testingId === wh.id}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition"
                      >
                        {testingId === wh.id ? "Sending..." : "Test Ping"}
                      </button>
                      <button
                        onClick={() => fetchDeliveries(wh)}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-cyan-400 text-xs font-medium rounded-lg transition"
                      >
                        Logs
                      </button>
                      {isAdmin && (
                        <button
                          onClick={() => handleDelete(wh.id)}
                          className="px-2.5 py-1 bg-red-950/40 hover:bg-red-900/60 text-red-400 border border-red-800/50 text-xs font-medium rounded-lg transition"
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Register Modal */}
        {isCreateOpen && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
              <h2 className="text-xl font-bold text-white">Register Webhook Endpoint</h2>
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Webhook Name</label>
                  <input
                    type="text"
                    required
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Audit Pipeline Receiver"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Destination URL (HTTP/HTTPS)</label>
                  <input
                    type="url"
                    required
                    value={formUrl}
                    onChange={(e) => setFormUrl(e.target.value)}
                    placeholder="https://api.external.com/webhooks/intelliflow"
                    className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-cyan-300 focus:outline-none focus:border-cyan-500"
                  />
                  <p className="text-xs text-slate-500 mt-1">Private IPs and internal Docker networks are blocked by SSRF filter.</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Subscribed Events (Comma-separated or &apos;*&apos;)</label>
                  <input
                    type="text"
                    value={formEventsStr}
                    onChange={(e) => setFormEventsStr(e.target.value)}
                    placeholder="document.created, workflow.completed, security.alert"
                    className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Description (Optional)</label>
                  <input
                    type="text"
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    placeholder="Informs third-party auditing engine"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsCreateOpen(false)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-xl transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium rounded-xl shadow-md transition"
                  >
                    Register Webhook
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Deliveries Modal */}
        {selectedWebhook && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                <div>
                  <h3 className="text-lg font-bold text-white">Delivery Logs: {selectedWebhook.name}</h3>
                  <p className="text-xs text-slate-400">{selectedWebhook.url}</p>
                </div>
                <button
                  onClick={() => setSelectedWebhook(null)}
                  className="text-slate-400 hover:text-white text-sm font-bold px-2 py-1"
                >
                  ✕
                </button>
              </div>

              <div className="overflow-y-auto flex-1 space-y-3">
                {deliveriesLoading ? (
                  <div className="text-center py-8 text-slate-500">Loading delivery attempts...</div>
                ) : deliveries.length === 0 ? (
                  <div className="text-center py-8 text-slate-500">No deliveries recorded yet.</div>
                ) : (
                  deliveries.map((deliv) => (
                    <div
                      key={deliv.id}
                      className="bg-slate-950 border border-slate-800/80 rounded-xl p-4 text-xs font-mono space-y-2"
                    >
                      <div className="flex justify-between items-center">
                        <span className="font-semibold text-white">{deliv.event_type}</span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                            deliv.status === "success"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          }`}
                        >
                          {deliv.status.toUpperCase()} ({deliv.response_status_code || "ERR"})
                        </span>
                      </div>
                      <div className="text-slate-400 flex justify-between">
                        <span>Duration: {deliv.duration_ms ?? 0}ms</span>
                        <span>{new Date(deliv.created_at).toLocaleString()}</span>
                      </div>
                      {deliv.error_message && (
                        <div className="p-2 bg-red-950/40 border border-red-800/50 text-red-300 rounded">
                          {deliv.error_message}
                        </div>
                      )}
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
