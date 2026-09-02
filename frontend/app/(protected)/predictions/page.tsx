"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useAuthStore } from "@/store/auth.store";
import {
  getPrediction,
  listPredictions,
  runPrediction,
} from "@/services/prediction.service";
import type {
  Prediction,
  PredictionModelName,
} from "@/types/analytics";

const MODELS: {
  id: PredictionModelName;
  name: string;
  desc: string;
  badge: string;
}[] = [
  {
    id: "revenue_forecast",
    name: "Revenue Forecast",
    desc: "Projects 12-month revenue, expense, and profit trajectories from departmental payroll data.",
    badge: "Financial",
  },
  {
    id: "employee_attrition",
    name: "Employee Attrition Risk",
    desc: "Heuristic estimation of attrition probability per department based on headcount dynamics and team size.",
    badge: "HR",
  },
  {
    id: "customer_churn",
    name: "Customer Churn Probability",
    desc: "Predicts churn likelihood from AI conversation frequency and document metadata engagement rates.",
    badge: "Engagement",
  },
];

export default function PredictionsPage() {
  const { user } = useAuthStore();
  const isAuthorized = Boolean(
    user?.role && ["admin", "manager", "hr", "finance"].includes(user.role.toLowerCase())
  );

  const [selectedModel, setSelectedModel] =
    useState<PredictionModelName>("revenue_forecast");
  const [running, setRunning] = useState(false);
  const [activeResult, setActiveResult] = useState<Prediction | null>(null);
  const [history, setHistory] = useState<Prediction[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    if (!isAuthorized) {
      setLoadingHistory(false);
      return;
    }
    try {
      setLoadingHistory(true);
      const res = await listPredictions({ page: 1, page_size: 20 });
      if (res.success) {
        setHistory(res.data);
      }
    } catch {
      // Non-blocking
    } finally {
      setLoadingHistory(false);
    }
  }, [isAuthorized]);

  useEffect(() => {
    if (isAuthorized) {
      fetchHistory();
    } else {
      setLoadingHistory(false);
    }
  }, [isAuthorized, fetchHistory]);

  const handleRun = async () => {
    if (!isAuthorized) return;
    try {
      setRunning(true);
      setError(null);
      const res = await runPrediction({ model: selectedModel });
      if (res.success) {
        setActiveResult(res.data);
        fetchHistory();
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to run prediction";
      setError(msg);
    } finally {
      setRunning(false);
    }
  };

  const handleSelectHistory = async (id: string) => {
    try {
      const res = await getPrediction(id);
      if (res.success) {
        setActiveResult(res.data);
      }
    } catch {
      // Ignore
    }
  };

  if (user && !isAuthorized) {
    return (
      <DashboardLayout
        title="AI Predictive Models"
        description="Deterministic statistical forecasting and risk estimation engines."
      >
        <div className="p-8 max-w-xl mx-auto my-12 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 flex items-center justify-center mx-auto text-amber-600 dark:text-amber-400">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v.01M12 9v4m-6.364 7.364A9 9 0 1118.364 5.636 9 9 0 015.636 20.364z" />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Access Restricted</h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Predictive modeling engines are reserved for Managers, HR, Finance, and Administrators.
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

  return (
    <DashboardLayout
      title="AI Predictive Models"
      description="Deterministic statistical forecasting and risk estimation engines."
    >
      <div className="space-y-8">
        {/* Model Selection Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {MODELS.map((m) => {
            const isSelected = selectedModel === m.id;
            return (
              <div
                key={m.id}
                onClick={() => setSelectedModel(m.id)}
                className={`cursor-pointer p-5 rounded-2xl border transition-all ${
                  isSelected
                    ? "bg-blue-50/50 dark:bg-blue-950/30 border-blue-500 shadow-md ring-1 ring-blue-500"
                    : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700"
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">
                    {m.badge}
                  </span>
                  <div
                    className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                      isSelected
                        ? "border-blue-600 bg-blue-600"
                        : "border-gray-300 dark:border-gray-600"
                    }`}
                  >
                    {isSelected && (
                      <div className="w-1.5 h-1.5 rounded-full bg-white" />
                    )}
                  </div>
                </div>
                <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-1.5">
                  {m.name}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                  {m.desc}
                </p>
              </div>
            );
          })}
        </div>

        {/* Action button */}
        <div className="flex items-center gap-4">
          <button
            onClick={handleRun}
            disabled={running}
            className="px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-all disabled:opacity-50 shadow-sm"
          >
            {running ? "Computing Forecast..." : `Run ${MODELS.find((m) => m.id === selectedModel)?.name}`}
          </button>
          {error && (
            <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>
          )}
        </div>

        {/* Active Prediction Result */}
        {activeResult && (
          <div className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 pb-4">
              <div>
                <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                  Prediction Output
                </span>
                <h3 className="text-lg font-bold text-gray-900 dark:text-white capitalize">
                  {activeResult.model.replace(/_/g, " ")}
                </h3>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Confidence Score
                </p>
                <p className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                  {activeResult.confidence !== null && activeResult.confidence !== undefined
                    ? `${(activeResult.confidence * 100).toFixed(1)}%`
                    : "N/A"}
                </p>
              </div>
            </div>

            {/* Structured view depending on model */}
            <div className="space-y-3">
              {activeResult.model === "revenue_forecast" &&
                Array.isArray(activeResult.prediction?.monthly_forecast) && (
                  <div>
                    <p className="text-xs text-gray-500 mb-2">
                      Annual Projected Revenue:{" "}
                      <strong className="text-gray-900 dark:text-white">
                        ${Number(activeResult.prediction?.total_annual_revenue_estimate ?? 0).toLocaleString()}
                      </strong>
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50 dark:bg-gray-800/50">
                          <tr>
                            <th className="px-3 py-2 text-left">Month</th>
                            <th className="px-3 py-2 text-left">Projected Revenue</th>
                            <th className="px-3 py-2 text-left">Projected Expenses</th>
                            <th className="px-3 py-2 text-left">Projected Profit</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                          {(
                            activeResult.prediction.monthly_forecast as Array<{
                              month: string;
                              projected_revenue: number;
                              projected_expenses: number;
                              projected_profit: number;
                            }>
                          ).map((m) => (
                            <tr key={m.month}>
                              <td className="px-3 py-2 font-medium">{m.month}</td>
                              <td className="px-3 py-2 text-emerald-600 font-medium">
                                ${m.projected_revenue.toLocaleString()}
                              </td>
                              <td className="px-3 py-2 text-rose-500">
                                ${m.projected_expenses.toLocaleString()}
                              </td>
                              <td className="px-3 py-2 text-blue-600 font-medium">
                                ${m.projected_profit.toLocaleString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

              {activeResult.model === "employee_attrition" && (
                <div className="space-y-4">
                  <div className="p-4 bg-gray-50 dark:bg-gray-800/40 rounded-xl flex items-center justify-between">
                    <div>
                      <p className="text-xs text-gray-500">Overall Risk Level</p>
                      <p className="text-xl font-bold text-gray-900 dark:text-white">
                        {String(activeResult.prediction?.overall_risk_label ?? "")} (
                        {(Number(activeResult.prediction?.overall_attrition_risk ?? 0) * 100).toFixed(1)}%)
                      </p>
                    </div>
                    <p className="text-xs text-gray-400">
                      Total Analyzed: {String(activeResult.prediction?.total_employees_analyzed ?? 0)} employees
                    </p>
                  </div>
                  {Array.isArray(activeResult.prediction?.department_breakdown) && (
                    <div className="space-y-2">
                      <p className="text-xs font-semibold text-gray-700 dark:text-gray-300">
                        Department Breakdown:
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {(
                          activeResult.prediction.department_breakdown as Array<{
                            department: string;
                            employee_count: number;
                            attrition_risk_score: number;
                            risk_label: string;
                          }>
                        ).map((d) => (
                          <div
                            key={d.department}
                            className="p-3 bg-gray-50 dark:bg-gray-800/30 rounded-xl border border-gray-100 dark:border-gray-800 flex items-center justify-between"
                          >
                            <div>
                              <p className="text-xs font-medium text-gray-900 dark:text-white">
                                {d.department}
                              </p>
                              <p className="text-[11px] text-gray-400">
                                {d.employee_count} employees
                              </p>
                            </div>
                            <span
                              className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
                                d.risk_label === "High"
                                  ? "bg-rose-100 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300"
                                  : d.risk_label === "Medium"
                                  ? "bg-amber-100 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300"
                                  : "bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300"
                              }`}
                            >
                              {d.risk_label}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}


              {activeResult.model === "customer_churn" && (
                <div className="space-y-4">
                  <div className="p-4 bg-gray-50 dark:bg-gray-800/40 rounded-xl flex items-center justify-between">
                    <div>
                      <p className="text-xs text-gray-500">Churn Probability</p>
                      <p className="text-2xl font-bold text-gray-900 dark:text-white">
                        {(Number(activeResult.prediction?.churn_probability) * 100).toFixed(1)}% (
                        {String(activeResult.prediction?.churn_label)})
                      </p>
                    </div>
                    <p className="text-xs text-gray-400">
                      Engagement Score: {String(activeResult.prediction?.engagement_score)}
                    </p>
                  </div>
                </div>
              )}
            </div>

            <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100 dark:border-gray-800">
              Computed in {activeResult.execution_time?.toFixed(3)}s · Model ID: {activeResult.id}
            </p>
          </div>
        )}

        {/* Prediction History Table */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
            Historical Forecast Log
          </h3>

          {loadingHistory ? (
            <LoadingSpinner message="Loading historical predictions..." />
          ) : history.length === 0 ? (
            <div className="p-8 text-center bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl text-gray-400 text-sm">
              No historical predictions found. Run a model above.
            </div>
          ) : (
            <div className="overflow-x-auto bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 dark:bg-gray-800/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Model
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Confidence
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Execution Time
                    </th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-400">
                      Timestamp
                    </th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-400">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {history.map((h) => (
                    <tr
                      key={h.id}
                      className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium text-gray-900 dark:text-white capitalize">
                        {h.model.replace(/_/g, " ")}
                      </td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                        {h.confidence !== null && h.confidence !== undefined
                          ? `${(h.confidence * 100).toFixed(0)}%`
                          : "-"}
                      </td>
                      <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                        {h.execution_time?.toFixed(3)}s
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {new Date(h.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleSelectHistory(h.id)}
                          className="text-blue-600 hover:text-blue-700 font-medium"
                        >
                          View Details
                        </button>
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
