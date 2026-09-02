"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useAuthStore } from "@/store/auth.store";
import {
  getAIUsageAnalytics,
  getDepartmentAnalytics,
  getDocumentAnalytics,
  getEmployeeAnalytics,
  getKPISummary,
  getRevenueAnalytics,
  getWorkflowAnalytics,
} from "@/services/analytics.service";
import type {
  AIUsageAnalytics,
  DepartmentAnalytics,
  DocumentAnalytics,
  EmployeeAnalytics,
  KPISummary,
  MonthlyRevenue,
  RevenueAnalytics,
  WorkflowAnalytics,
} from "@/types/analytics";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtNum(n: number) {
  return n.toLocaleString();
}

function fmtCurrency(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);
}


// ---------------------------------------------------------------------------
// Tiny bar-chart component (CSS-only, no external lib)
// ---------------------------------------------------------------------------

function BarChart<T extends object>({
  data,
  labelKey,
  valueKey,
  color = "#2563EB",
  maxValue,
}: {
  data: T[];
  labelKey: string;
  valueKey: string;
  color?: string;
  maxValue?: number;
}) {
  const max = maxValue ?? Math.max(...data.map((d) => Number((d as Record<string, unknown>)[valueKey]) || 0), 1);
  return (
    <div className="space-y-2">
      {data.map((item, i) => {
        const val = Number((item as Record<string, unknown>)[valueKey]) || 0;
        const pct = Math.round((val / max) * 100);
        return (
          <div key={i} className="flex items-center gap-3">
            <span className="w-8 text-[10px] text-gray-500 dark:text-gray-400 shrink-0 text-right">
              {String((item as Record<string, unknown>)[labelKey]).slice(0, 3)}
            </span>
            <div className="flex-1 h-5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
            <span className="w-14 text-[11px] font-medium text-gray-700 dark:text-gray-300 text-right">
              {fmtNum(val)}
            </span>
          </div>
        );
      })}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Revenue dual-bar chart
// ---------------------------------------------------------------------------

function RevenueChart({ data }: { data: MonthlyRevenue[] }) {
  const maxVal = Math.max(
    ...data.map((d) => Math.max(d.revenue, d.expenses)),
    1,
  );
  return (
    <div className="space-y-2">
      {data.map((item, i) => (
        <div key={i} className="grid grid-cols-[2rem_1fr_1fr_5rem] gap-2 items-center">
          <span className="text-[10px] text-gray-500 dark:text-gray-400 text-right">
            {item.month}
          </span>
          {/* Revenue bar */}
          <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all duration-700"
              style={{ width: `${Math.round((item.revenue / maxVal) * 100)}%` }}
            />
          </div>
          {/* Expenses bar */}
          <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-rose-400 transition-all duration-700"
              style={{ width: `${Math.round((item.expenses / maxVal) * 100)}%` }}
            />
          </div>
          <span className="text-[10px] text-gray-500 dark:text-gray-400 text-right">
            {fmtCurrency(item.profit)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Donut / status breakdown
// ---------------------------------------------------------------------------

function StatusPills({ items }: { items: { status: string; count: number }[] }) {
  const total = items.reduce((s, i) => s + i.count, 0) || 1;
  const COLORS = [
    "#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4",
  ];
  return (
    <div className="space-y-2">
      {items.map((item, i) => {
        const pct = Math.round((item.count / total) * 100);
        return (
          <div key={i} className="flex items-center gap-3">
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: COLORS[i % COLORS.length] }}
            />
            <span className="flex-1 text-xs text-gray-700 dark:text-gray-300 capitalize">
              {item.status.replace(/_/g, " ")}
            </span>
            <span className="text-xs font-semibold text-gray-900 dark:text-white">
              {fmtNum(item.count)}
            </span>
            <div className="w-16 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{ width: `${pct}%`, backgroundColor: COLORS[i % COLORS.length] }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPI Card
// ---------------------------------------------------------------------------

function KPICard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center mb-3 text-white text-lg font-bold"
        style={{ background: color }}
      >
        {String(value)[0]}
      </div>
      <p className="text-2xl font-bold text-gray-900 dark:text-white">
        {typeof value === "number" ? fmtNum(value) : value}
      </p>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{label}</p>
      {sub && (
        <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1">{sub}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-6 shadow-sm">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">
        {title}
      </h3>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

type Tab =
  | "overview"
  | "revenue"
  | "departments"
  | "employees"
  | "documents"
  | "workflows"
  | "ai";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "revenue", label: "Revenue" },
  { id: "departments", label: "Departments" },
  { id: "employees", label: "Employees" },
  { id: "documents", label: "Documents" },
  { id: "workflows", label: "Workflows" },
  { id: "ai", label: "AI Usage" },
];

export default function AnalyticsPage() {
  const { user } = useAuthStore();
  const isAuthorized = Boolean(
    user?.role && ["admin", "manager", "hr", "finance"].includes(user.role.toLowerCase())
  );

  const [tab, setTab] = useState<Tab>("overview");
  const [kpi, setKpi] = useState<KPISummary | null>(null);
  const [revenue, setRevenue] = useState<RevenueAnalytics | null>(null);
  const [departments, setDepartments] = useState<DepartmentAnalytics | null>(null);
  const [employees, setEmployees] = useState<EmployeeAnalytics | null>(null);
  const [documents, setDocuments] = useState<DocumentAnalytics | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowAnalytics | null>(null);
  const [aiUsage, setAiUsage] = useState<AIUsageAnalytics | null>(null);
  const [loading, setLoading] = useState<Record<Tab, boolean>>({
    overview: false,
    revenue: false,
    departments: false,
    employees: false,
    documents: false,
    workflows: false,
    ai: false,
  });
  const [errors, setErrors] = useState<Record<Tab, string | null>>({
    overview: null,
    revenue: null,
    departments: null,
    employees: null,
    documents: null,
    workflows: null,
    ai: null,
  });

  const setTabLoading = (t: Tab, v: boolean) =>
    setLoading((p) => ({ ...p, [t]: v }));
  const setTabError = (t: Tab, v: string | null) =>
    setErrors((p) => ({ ...p, [t]: v }));

  const loadOverview = useCallback(async () => {
    if (kpi || !isAuthorized) return;
    setTabLoading("overview", true);
    setTabError("overview", null);
    try {
      const res = await getKPISummary();
      if (res.success) setKpi(res.data);
    } catch {
      setTabError("overview", "Failed to load KPI data. Ensure you have the required role.");
    } finally {
      setTabLoading("overview", false);
    }
  }, [kpi, isAuthorized]);

  const loadRevenue = useCallback(async () => {
    if (revenue || !isAuthorized) return;
    setTabLoading("revenue", true);
    try {
      const res = await getRevenueAnalytics();
      if (res.success) setRevenue(res.data);
    } catch {
      setTabError("revenue", "Failed to load revenue data.");
    } finally {
      setTabLoading("revenue", false);
    }
  }, [revenue, isAuthorized]);

  const loadDepartments = useCallback(async () => {
    if (departments || !isAuthorized) return;
    setTabLoading("departments", true);
    try {
      const res = await getDepartmentAnalytics();
      if (res.success) setDepartments(res.data);
    } catch {
      setTabError("departments", "Failed to load department data.");
    } finally {
      setTabLoading("departments", false);
    }
  }, [departments, isAuthorized]);

  const loadEmployees = useCallback(async () => {
    if (employees || !isAuthorized) return;
    setTabLoading("employees", true);
    try {
      const res = await getEmployeeAnalytics();
      if (res.success) setEmployees(res.data);
    } catch {
      setTabError("employees", "Failed to load employee data.");
    } finally {
      setTabLoading("employees", false);
    }
  }, [employees, isAuthorized]);

  const loadDocuments = useCallback(async () => {
    if (documents || !isAuthorized) return;
    setTabLoading("documents", true);
    try {
      const res = await getDocumentAnalytics();
      if (res.success) setDocuments(res.data);
    } catch {
      setTabError("documents", "Failed to load document data.");
    } finally {
      setTabLoading("documents", false);
    }
  }, [documents, isAuthorized]);

  const loadWorkflows = useCallback(async () => {
    if (workflows || !isAuthorized) return;
    setTabLoading("workflows", true);
    try {
      const res = await getWorkflowAnalytics();
      if (res.success) setWorkflows(res.data);
    } catch {
      setTabError("workflows", "Failed to load workflow data.");
    } finally {
      setTabLoading("workflows", false);
    }
  }, [workflows, isAuthorized]);

  const loadAI = useCallback(async () => {
    if (aiUsage || !isAuthorized) return;
    setTabLoading("ai", true);
    try {
      const res = await getAIUsageAnalytics();
      if (res.success) setAiUsage(res.data);
    } catch {
      setTabError("ai", "Failed to load AI usage data.");
    } finally {
      setTabLoading("ai", false);
    }
  }, [aiUsage, isAuthorized]);

  useEffect(() => {
    if (!isAuthorized) return;
    if (tab === "overview") loadOverview();
    else if (tab === "revenue") loadRevenue();
    else if (tab === "departments") loadDepartments();
    else if (tab === "employees") loadEmployees();
    else if (tab === "documents") loadDocuments();
    else if (tab === "workflows") loadWorkflows();
    else if (tab === "ai") loadAI();
  }, [tab, isAuthorized, loadOverview, loadRevenue, loadDepartments, loadEmployees, loadDocuments, loadWorkflows, loadAI]);

  if (user && !isAuthorized) {
    return (
      <DashboardLayout
        title="Analytics"
        description="Comprehensive data-driven insights across all platform dimensions."
      >
        <div className="p-8 max-w-xl mx-auto my-12 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 flex items-center justify-center mx-auto text-amber-600 dark:text-amber-400">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v.01M12 9v4m-6.364 7.364A9 9 0 1118.364 5.636 9 9 0 015.636 20.364z" />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Access Restricted</h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Analytics and KPI summaries are reserved for Managers, HR, Finance, and Administrators.
          </p>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl transition-all shadow-sm"
          >
            Return to Dashboard
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  const isLoading = loading[tab];
  const error = errors[tab];

  return (
    <DashboardLayout
      title="Analytics"
      description="Comprehensive data-driven insights across all platform dimensions."
    >
      {/* Tab bar */}
      <div className="flex gap-1 p-1 bg-gray-100 dark:bg-gray-800/60 rounded-xl mb-6 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${
              tab === t.id
                ? "bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 shadow-sm"
                : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading && <LoadingSpinner message={`Loading ${tab} analytics…`} />}

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
          {error}
        </div>
      )}

      {!isLoading && !error && (
        <>
          {/* ---- Overview ---- */}
          {tab === "overview" && kpi && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                <KPICard label="Employees" value={kpi.total_employees} color="#2563EB" />
                <KPICard label="Documents" value={kpi.total_documents} color="#10B981" />
                <KPICard label="Active Workflows" value={kpi.active_workflows} color="#8B5CF6" />
                <KPICard label="AI Conversations" value={kpi.total_ai_conversations} color="#F59E0B" />
                <KPICard label="Completed Executions" value={kpi.completed_workflow_executions} color="#06B6D4" />
                <KPICard label="Predictions Run" value={kpi.total_predictions_run} color="#EC4899" />
                <KPICard label="Reports Generated" value={kpi.total_reports_generated} color="#EF4444" />
              </div>
            </div>
          )}

          {/* ---- Revenue ---- */}
          {tab === "revenue" && revenue && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Section title="Year">
                  <p className="text-3xl font-bold text-gray-900 dark:text-white">{revenue.year}</p>
                </Section>
                <Section title="Total Expenses YTD">
                  <p className="text-3xl font-bold text-rose-600">{fmtCurrency(revenue.total_expenses_ytd)}</p>
                </Section>
                <Section title="Avg Monthly Expenses">
                  <p className="text-3xl font-bold text-amber-600">{fmtCurrency(revenue.avg_monthly_expenses)}</p>
                </Section>
              </div>
              <Section title="Monthly Revenue vs Expenses (Estimated)">
                <div className="flex gap-4 text-xs mb-4">
                  <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-emerald-500" /> Revenue (est.)</span>
                  <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-rose-400" /> Expenses</span>
                  <span className="text-gray-400 ml-auto">Profit (right)</span>
                </div>
                <RevenueChart data={revenue.data} />
              </Section>
            </div>
          )}

          {/* ---- Departments ---- */}
          {tab === "departments" && departments && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {fmtNum(departments.total_departments)} departments total
              </p>
              <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-800/60">
                    <tr>
                      {["Department", "Employees", "Avg Salary", "Documents", "Workflows"].map((h) => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                    {departments.data.map((d) => (
                      <tr key={d.department_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors">
                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{d.department_name}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{fmtNum(d.employee_count)}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{fmtCurrency(d.avg_salary)}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{fmtNum(d.document_count)}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{fmtNum(d.active_workflows)}</td>
                      </tr>
                    ))}
                    {departments.data.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                          No department data available.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ---- Employees ---- */}
          {tab === "employees" && employees && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "Total", value: employees.total, color: "#2563EB" },
                    { label: "Active", value: employees.active, color: "#10B981" },
                    { label: "New This Month", value: employees.new_this_month, color: "#F59E0B" },
                  ].map((s) => (
                    <div key={s.label} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 text-center">
                      <p className="text-2xl font-bold" style={{ color: s.color }}>{fmtNum(s.value)}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{s.label}</p>
                    </div>
                  ))}
                </div>
                <Section title="Role Distribution">
                  <StatusPills items={employees.role_distribution.map((r) => ({ status: r.role, count: r.count }))} />
                </Section>
              </div>
              <Section title="Monthly Headcount">
                <BarChart data={employees.monthly_headcount} labelKey="month" valueKey="count" color="#2563EB" />
              </Section>
            </div>
          )}

          {/* ---- Documents ---- */}
          {tab === "documents" && documents && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <Section title="Total Uploads">
                  <p className="text-4xl font-bold text-gray-900 dark:text-white">{fmtNum(documents.total_uploads)}</p>
                </Section>
                <Section title="By Processing Status">
                  <StatusPills items={documents.by_status} />
                </Section>
                <Section title="By OCR Status">
                  <StatusPills items={documents.by_ocr_status} />
                </Section>
              </div>
              <Section title="Monthly Upload Trend">
                <BarChart data={documents.monthly_uploads} labelKey="month" valueKey="count" color="#10B981" />
              </Section>
            </div>
          )}

          {/* ---- Workflows ---- */}
          {tab === "workflows" && workflows && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 text-center">
                    <p className="text-3xl font-bold text-purple-600">{fmtNum(workflows.total_executions)}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Total Executions</p>
                  </div>
                  <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 text-center">
                    <p className="text-3xl font-bold text-cyan-600">{workflows.avg_duration_seconds.toFixed(1)}s</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Avg Duration</p>
                  </div>
                </div>
                <Section title="Execution Status Breakdown">
                  <StatusPills items={workflows.by_status} />
                </Section>
              </div>
              <Section title="Step Action Frequency">
                <BarChart data={workflows.step_action_frequency} labelKey="status" valueKey="count" color="#8B5CF6" />
              </Section>
            </div>
          )}

          {/* ---- AI Usage ---- */}
          {tab === "ai" && aiUsage && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: "Total Conversations", value: fmtNum(aiUsage.total_conversations), color: "#8B5CF6" },
                    { label: "Avg Response Time", value: `${aiUsage.avg_response_time_seconds.toFixed(2)}s`, color: "#06B6D4" },
                    { label: "Prompt Tokens", value: fmtNum(aiUsage.total_prompt_tokens), color: "#F59E0B" },
                    { label: "Completion Tokens", value: fmtNum(aiUsage.total_completion_tokens), color: "#10B981" },
                  ].map((s) => (
                    <div key={s.label} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 text-center">
                      <p className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{s.label}</p>
                    </div>
                  ))}
                </div>
              </div>
              <Section title="Monthly Conversations">
                <BarChart data={aiUsage.monthly_conversations} labelKey="month" valueKey="count" color="#8B5CF6" />
              </Section>
            </div>
          )}
        </>
      )}
    </DashboardLayout>
  );
}
