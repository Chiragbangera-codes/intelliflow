"use client";

import React, { useCallback, useEffect, useState } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import {
  getReport,
  listReports,
  requestReport,
} from "@/services/report.service";
import type {
  Report,
  ReportFormatName,
  ReportTypeName,
} from "@/types/analytics";

const REPORT_TYPES: { id: ReportTypeName; label: string; desc: string }[] = [
  {
    id: "revenue",
    label: "Financial & Revenue Report",
    desc: "Payroll-derived expenses, estimated revenues, and quarterly profit estimates.",
  },
  {
    id: "employees",
    label: "Employee Directory & Compensation",
    desc: "Active personnel directory with designations, salaries, and join dates.",
  },
  {
    id: "departments",
    label: "Departmental Performance",
    desc: "Department summaries with headcount, document ownership, and active workflow metrics.",
  },
  {
    id: "workflows",
    label: "Workflow & Automation Summary",
    desc: "Execution counts, success rates, failure metrics, and average runtimes.",
  },
  {
    id: "documents",
    label: "Document Processing & OCR Audit",
    desc: "Storage logs, OCR processing status, owner breakdown, and file sizes.",
  },
  {
    id: "ai_usage",
    label: "AI Assistant & LLM Consumption",
    desc: "Conversation frequency, token usage metrics, and response latencies.",
  },
];

const FORMATS: { id: ReportFormatName; label: string }[] = [
  { id: "csv", label: "CSV (.csv)" },
  { id: "xlsx", label: "Excel (.xlsx)" },
  { id: "pdf", label: "PDF (.pdf)" },
];

export default function ReportsPage() {
  const [selectedType, setSelectedType] = useState<ReportTypeName>("revenue");
  const [selectedFormat, setSelectedFormat] =
    useState<ReportFormatName>("csv");
  const [requesting, setRequesting] = useState(false);
  const [reports, setReports] = useState<Report[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchReports = useCallback(async () => {
    try {
      setLoadingList(true);
      const res = await listReports({ page: 1, page_size: 20 });
      if (res.success) {
        setReports(res.data);
      }
    } catch {
      // Non-blocking
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  // Periodic polling for pending reports
  useEffect(() => {
    const hasPending = reports.some((r) => r.status === "pending");
    if (!hasPending) return;

    const interval = setInterval(async () => {
      for (const r of reports.filter((x) => x.status === "pending")) {
        try {
          const res = await getReport(r.id);
          if (res.success && res.data.status !== "pending") {
            setReports((prev) =>
              prev.map((item) => (item.id === r.id ? res.data : item)),
            );
          }
        } catch {
          // Ignore
        }
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [reports]);

  const handleGenerate = async () => {
    try {
      setRequesting(true);
      setError(null);
      setSuccessMsg(null);
      const res = await requestReport({
        report_type: selectedType,
        format: selectedFormat,
      });
      if (res.success) {
        setSuccessMsg(
          "Report generation initiated. The background job is compiling your file.",
        );
        fetchReports();
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to request report";
      setError(msg);
    } finally {
      setRequesting(false);
    }
  };

  return (
    <DashboardLayout
      title="Export & Reports Generator"
      description="Compile and export structured operational datasets in CSV, Excel, and PDF formats."
    >
      <div className="space-y-8">
        {/* Request Form */}
        <div className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm space-y-5">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
            Generate New Report
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Report Type */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300">
                Dataset Category
              </label>
              <select
                value={selectedType}
                onChange={(e) =>
                  setSelectedType(e.target.value as ReportTypeName)
                }
                className="w-full px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {REPORT_TYPES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-gray-400">
                {REPORT_TYPES.find((t) => t.id === selectedType)?.desc}
              </p>
            </div>

            {/* Format Selection */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-gray-700 dark:text-gray-300">
                File Format
              </label>
              <div className="flex gap-3">
                {FORMATS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setSelectedFormat(f.id)}
                    className={`flex-1 py-2.5 rounded-xl text-xs font-medium border transition-all ${
                      selectedFormat === f.id
                        ? "bg-blue-50 dark:bg-blue-950/40 border-blue-500 text-blue-600 dark:text-blue-400 font-semibold"
                        : "border-gray-200 dark:border-gray-800 text-gray-600 dark:text-gray-400 hover:border-gray-300"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 pt-2">
            <button
              onClick={handleGenerate}
              disabled={requesting}
              className="px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-all disabled:opacity-50 shadow-sm"
            >
              {requesting ? "Submitting Request..." : "Request Report Compilation"}
            </button>
            {successMsg && (
              <p className="text-xs text-emerald-600 dark:text-emerald-400">
                {successMsg}
              </p>
            )}
            {error && (
              <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>
            )}
          </div>
        </div>

        {/* Report Queue / History */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              Generated Reports &amp; Exports
            </h3>
            <button
              onClick={fetchReports}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              Refresh Status
            </button>
          </div>

          {loadingList ? (
            <LoadingSpinner message="Loading reports..." />
          ) : reports.length === 0 ? (
            <div className="p-8 text-center bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl text-gray-400 text-sm">
              No reports compiled yet. Select a dataset above to generate one.
            </div>
          ) : (
            <div className="overflow-x-auto bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 dark:bg-gray-800/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Report Dataset
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Format
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Created
                    </th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-400">
                      Output
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {reports.map((r) => (
                    <tr
                      key={r.id}
                      className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium text-gray-900 dark:text-white capitalize">
                        {r.report_type.replace(/_/g, " ")}
                      </td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300 uppercase font-mono">
                        {r.format || "CSV"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium capitalize ${
                            r.status === "completed"
                              ? "bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300"
                              : r.status === "pending"
                              ? "bg-amber-100 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300"
                              : "bg-rose-100 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300"
                          }`}
                        >
                          {r.status === "pending" && (
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                          )}
                          {r.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {new Date(r.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {r.status === "completed" && r.file_path ? (
                          <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-mono truncate max-w-xs inline-block">
                            {r.file_path.split("/").pop()}
                          </span>
                        ) : r.status === "pending" ? (
                          <span className="text-gray-400 italic">Processing…</span>
                        ) : (
                          <span className="text-rose-400 italic">Failed</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
