"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/store/auth.store";
import {
  getEvents,
  getOutboxStats,
} from "@/services/event.service";
import type {
  OutboxStats,
  PlatformEvent,
} from "@/types/event";
import ErrorBoundary from "@/components/ui/ErrorBoundary";

function ActivityIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
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

export default function EventsAdminPage() {
  const { user, isInitializing, isAuthenticated } = useAuthStore();
  const [events, setEvents] = useState<PlatformEvent[]>([]);
  const [outboxStats, setOutboxStats] = useState<OutboxStats | null>(null);
  const [loading, setLoading] = useState(true);

  // Selected event for payload inspector
  const [selectedEvent, setSelectedEvent] = useState<PlatformEvent | null>(null);

  const role = user?.role?.toLowerCase() || "";
  const isAuthorized = ["admin", "manager"].includes(role);

  const fetchTelemetry = useCallback(async () => {
    if (!isAuthorized) return;
    setLoading(true);
    try {
      const [eventsRes, statsRes] = await Promise.all([
        getEvents(1, 50),
        getOutboxStats(),
      ]);
      setEvents(eventsRes.items);
      setOutboxStats(statsRes);
    } catch {
      // Ignored
    } finally {
      setLoading(false);
    }
  }, [isAuthorized]);

  useEffect(() => {
    if (!isInitializing && isAuthenticated && isAuthorized) {
      fetchTelemetry();
    }
  }, [isInitializing, isAuthenticated, isAuthorized, fetchTelemetry]);

  if (!isInitializing && !isAuthorized) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-red-950/40 border border-red-800/60 rounded-xl p-6 text-center text-red-300">
          <h2 className="text-xl font-bold mb-2">Access Restricted</h2>
          <p>Event Bus & Outbox Telemetry is reserved for Administrators and Managers.</p>
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
            <div className="p-3 bg-purple-500/10 border border-purple-500/20 rounded-xl text-purple-400">
              <ActivityIcon className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Event Bus & Outbox Activity</h1>
              <p className="text-sm text-slate-400">
                End-to-end event stream tracing and transactional outbox queue health metrics.
              </p>
            </div>
          </div>
          <button
            onClick={fetchTelemetry}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-xl border border-slate-700 transition"
          >
            <RefreshIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh Stream
          </button>
        </div>

        {/* Outbox Queue Telemetry Cards */}
        {outboxStats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 backdrop-blur-sm">
              <span className="text-xs text-slate-400">Outbox Pending</span>
              <div className="text-2xl font-bold text-amber-400 mt-1">{outboxStats.pending}</div>
            </div>
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 backdrop-blur-sm">
              <span className="text-xs text-slate-400">Outbox Processing</span>
              <div className="text-2xl font-bold text-cyan-400 mt-1">{outboxStats.processing}</div>
            </div>
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 backdrop-blur-sm">
              <span className="text-xs text-slate-400">Total Processed</span>
              <div className="text-2xl font-bold text-emerald-400 mt-1">{outboxStats.processed}</div>
            </div>
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 backdrop-blur-sm">
              <span className="text-xs text-slate-400">Retrying (Backoff)</span>
              <div className="text-2xl font-bold text-orange-400 mt-1">{outboxStats.failed}</div>
            </div>
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 backdrop-blur-sm">
              <span className="text-xs text-slate-400">Dead Letter Queue</span>
              <div className="text-2xl font-bold text-rose-400 mt-1">{outboxStats.dead_letter}</div>
            </div>
          </div>
        )}

        {/* Events Table */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden backdrop-blur-sm shadow-xl">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/80 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="px-6 py-4">Event Type</th>
                <th className="px-6 py-4">Source</th>
                <th className="px-6 py-4">Correlation ID</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Timestamp</th>
                <th className="px-6 py-4 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-500">
                    Loading event stream...
                  </td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-500">
                    No platform events recorded yet.
                  </td>
                </tr>
              ) : (
                events.map((ev) => (
                  <tr key={ev.id} className="hover:bg-slate-800/30 transition">
                    <td className="px-6 py-4 font-mono font-semibold text-white">
                      {ev.event_type}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-400">{ev.source}</td>
                    <td className="px-6 py-4 font-mono text-xs text-cyan-400 max-w-xs truncate">
                      {ev.correlation_id}
                    </td>
                    <td className="px-6 py-4">
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {ev.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-400">
                      {new Date(ev.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => setSelectedEvent(ev)}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-purple-400 text-xs font-medium rounded-lg transition"
                      >
                        Payload
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Payload Inspector Modal */}
        {selectedEvent && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                <div>
                  <h3 className="text-lg font-bold text-white">Event: {selectedEvent.event_type}</h3>
                  <p className="text-xs font-mono text-slate-400">ID: {selectedEvent.id}</p>
                </div>
                <button
                  onClick={() => setSelectedEvent(null)}
                  className="text-slate-400 hover:text-white text-sm font-bold px-2 py-1"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-2 text-xs">
                <div className="flex justify-between text-slate-400 font-mono">
                  <span>Correlation ID:</span>
                  <span className="text-cyan-400">{selectedEvent.correlation_id}</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Actor ID:</span>
                  <span>{selectedEvent.actor_id || "System"}</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Payload Content (JSON)</label>
                <pre className="w-full font-mono text-xs bg-slate-950 border border-slate-800 rounded-xl p-4 text-emerald-400 overflow-x-auto max-h-64">
                  {JSON.stringify(selectedEvent.payload, null, 2)}
                </pre>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={() => setSelectedEvent(null)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium rounded-xl"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
