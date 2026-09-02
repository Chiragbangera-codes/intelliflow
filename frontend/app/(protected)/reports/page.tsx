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
    <DashboardLayout>
      <div style={{ maxWidth: 1200 }}>
        {/* Page Header */}
        <div style={{ marginBottom: 40 }}>
          <p className="eyebrow" style={{ color: "var(--accent)", marginBottom: 12 }}>
            Intelligence & Reports
          </p>
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
            Exports &
            <br />
            <span style={{ color: "var(--ink-40)" }}>structured report datasets.</span>
          </h1>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 36 }}>
          {/* Request Form */}
          <div
            style={{
              background: "var(--ink-90)",
              border: "1px solid var(--ink-70)",
              borderRadius: 12,
              padding: "28px",
            }}
          >
            <h3
              style={{
                fontSize: 14,
                fontWeight: 700,
                letterSpacing: "-0.01em",
                color: "#f1f5f9",
                marginBottom: 20,
              }}
            >
              Compile New Report
            </h3>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>
              {/* Report Type */}
              <div>
                <label className="input-label">Dataset Category</label>
                <select
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value as ReportTypeName)}
                  className="input"
                >
                  {REPORT_TYPES.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <p style={{ fontSize: 11, color: "var(--ink-40)", marginTop: 6 }}>
                  {REPORT_TYPES.find((t) => t.id === selectedType)?.desc}
                </p>
              </div>

              {/* Format Selection */}
              <div>
                <label className="input-label">File Format</label>
                <div style={{ display: "flex", gap: 8 }}>
                  {FORMATS.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setSelectedFormat(f.id)}
                      className={selectedFormat === f.id ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
                      style={{ flex: 1 }}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <button
                onClick={handleGenerate}
                disabled={requesting}
                className="btn btn-primary"
              >
                {requesting ? "Submitting Request..." : "Request Report Compilation"}
              </button>
              {successMsg && (
                <p style={{ fontSize: 12, color: "#4ade80", margin: 0 }}>
                  {successMsg}
                </p>
              )}
              {error && (
                <p style={{ fontSize: 12, color: "#f87171", margin: 0 }}>{error}</p>
              )}
            </div>
          </div>

          {/* Report Queue / History */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <h3
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                  color: "var(--ink-40)",
                  margin: 0,
                }}
              >
                Generated Reports &amp; Exports
              </h3>
              <button
                onClick={fetchReports}
                className="btn btn-ghost btn-sm"
              >
                Refresh Status
              </button>
            </div>

            {loadingList ? (
              <LoadingSpinner size="md" message="Loading reports..." />
            ) : reports.length === 0 ? (
              <div style={{ padding: "40px 24px", textAlign: "center", background: "var(--ink-90)", border: "1px solid var(--ink-70)", borderRadius: 12, color: "var(--ink-40)", fontSize: 13 }}>
                No reports compiled yet. Select a dataset above to generate one.
              </div>
            ) : (
              <div style={{ background: "var(--ink-90)", border: "1px solid var(--ink-70)", borderRadius: 12, overflow: "hidden" }}>
                <div style={{ overflowX: "auto" }}>
                  <table className="table-enterprise">
                    <thead>
                      <tr>
                        <th>Report Dataset</th>
                        <th>Format</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th style={{ textAlign: "right" }}>Output</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reports.map((r) => (
                        <tr key={r.id}>
                          <td style={{ fontWeight: 600, color: "#f1f5f9", textTransform: "capitalize" }}>
                            {r.report_type.replace(/_/g, " ")}
                          </td>
                          <td style={{ fontFamily: "monospace", fontSize: 11, textTransform: "uppercase" }}>
                            {r.format || "CSV"}
                          </td>
                          <td>
                            <span
                              className={`badge ${
                                r.status === "completed"
                                  ? "badge-active"
                                  : r.status === "pending"
                                  ? "badge-draft"
                                  : "badge-expired"
                              }`}
                            >
                              {r.status}
                            </span>
                          </td>
                          <td style={{ fontSize: 12 }}>
                            {new Date(r.created_at).toLocaleString()}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            {r.status === "completed" && r.file_path ? (
                              <span style={{ fontSize: 11, color: "#4ade80", fontFamily: "monospace" }}>
                                {r.file_path.split("/").pop()}
                              </span>
                            ) : r.status === "pending" ? (
                              <span style={{ color: "var(--ink-40)", fontStyle: "italic", fontSize: 11 }}>Processing…</span>
                            ) : (
                              <span style={{ color: "#f87171", fontStyle: "italic", fontSize: 11 }}>Failed</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
