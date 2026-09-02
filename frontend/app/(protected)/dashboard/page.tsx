"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { StatCard } from "@/components/ui/StatCard";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { AIChat } from "@/components/ai/AIChat";
import { useAuthStore } from "@/store/auth.store";
import { getDashboardStats } from "@/services/dashboard.service";
import type { DashboardStats } from "@/types";

export default function DashboardPage() {
  const { user } = useAuthStore();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStats() {
      try {
        setLoading(true);
        const res = await getDashboardStats();
        if (res.success) {
          setStats(res.data);
        }
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : "Failed to load dashboard stats";
        setError(errorMsg);
      } finally {
        setLoading(false);
      }
    }

    loadStats();
  }, []);

  return (
    <DashboardLayout
      title="Platform Overview"
      description={`Welcome back, ${user?.first_name || "User"}. Here is what's happening today.`}
    >
      <div className="space-y-8">
        {/* KPI Metrics */}
        {loading ? (
          <LoadingSpinner message="Loading dashboard statistics..." />
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
            {error}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              title="Total Departments"
              value={stats?.total_departments ?? 0}
              description="Active organizational divisions"
              icon={
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                  />
                </svg>
              }
            />

            <StatCard
              title="Employee Profiles"
              value={stats?.total_employees ?? 0}
              description="Registered workforce profiles"
              icon={
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"
                  />
                </svg>
              }
            />

            <StatCard
              title={user?.role === "admin" || user?.role === "hr" ? "Total Documents" : "My Documents"}
              value={stats?.total_documents ?? 0}
              description={
                user?.role === "admin" || user?.role === "hr"
                  ? "Global document metadata index"
                  : "Metadata records in your vault"
              }
              icon={
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              }
            />

            <StatCard
              title="Active Workflows"
              value={stats?.total_workflows ?? 0}
              description={`${stats?.pending_executions ?? 0} active running/pending`}
              icon={
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
              }
            />
          </div>
        )}

        {/* IntelliFlow AI — Milestone 7 */}
        <div>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-sm shrink-0">
              <span className="text-white text-sm font-bold">✦</span>
            </div>
            <div>
              <h2 className="text-sm font-bold text-gray-900 dark:text-white">
                IntelliFlow AI
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                Ask questions about your documents — answers grounded in your authorized files only
              </p>
            </div>
            <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-100 dark:bg-violet-900/50 text-violet-700 dark:text-violet-300 text-[10px] font-semibold uppercase tracking-wider">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse" />
              AI Assistant
            </span>
          </div>
          <AIChat defaultTopK={5} />
        </div>

        {/* Quick Navigation Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          <Link
            href="/departments"
            className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm hover:border-blue-500 hover:shadow-md transition-all group"
          >
            <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/50 flex items-center justify-center text-blue-600 dark:text-blue-400 mb-4 group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white group-hover:text-blue-600 transition-colors">
              Manage Departments
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
              Organize company units, assign team members, and view departmental hierarchy.
            </p>
          </Link>

          <Link
            href="/employees"
            className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm hover:border-blue-500 hover:shadow-md transition-all group"
          >
            <div className="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-950/50 flex items-center justify-center text-emerald-600 dark:text-emerald-400 mb-4 group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white group-hover:text-emerald-600 transition-colors">
              Employee Directory
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
              Access HR profiles, designations, contact data, and reporting lines.
            </p>
          </Link>

          <Link
            href="/documents"
            className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm hover:border-blue-500 hover:shadow-md transition-all group"
          >
            <div className="w-10 h-10 rounded-xl bg-cyan-50 dark:bg-cyan-950/50 flex items-center justify-center text-cyan-600 dark:text-cyan-400 mb-4 group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white group-hover:text-cyan-600 transition-colors">
              Document Metadata
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
              Track uploaded files, check storage checksums, and monitor processing pipelines.
            </p>
          </Link>

          <Link
            href="/workflows"
            className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm hover:border-blue-500 hover:shadow-md transition-all group"
          >
            <div className="w-10 h-10 rounded-xl bg-purple-50 dark:bg-purple-950/50 flex items-center justify-center text-purple-600 dark:text-purple-400 mb-4 group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white group-hover:text-purple-600 transition-colors">
              Workflows &amp; Automation
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
              Design automated pipelines with approval gates, notifications, and document actions.
            </p>
          </Link>

          <Link
            href="/analytics"
            className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm hover:border-blue-500 hover:shadow-md transition-all group"
          >
            <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 mb-4 group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white group-hover:text-indigo-600 transition-colors">
              Operational Analytics
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
              7-dimensional aggregate dashboards covering financials, headcount, workflows, and AI.
            </p>
          </Link>

          <Link
            href="/predictions"
            className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm hover:border-blue-500 hover:shadow-md transition-all group"
          >
            <div className="w-10 h-10 rounded-xl bg-amber-50 dark:bg-amber-950/50 flex items-center justify-center text-amber-600 dark:text-amber-400 mb-4 group-hover:scale-110 transition-transform">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white group-hover:text-amber-600 transition-colors">
              AI Forecasts &amp; Predictions
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed">
              Revenue trajectories, employee attrition risks, and customer churn probabilities.
            </p>
          </Link>
        </div>

        {/* Milestone Status Banner */}
        <div className="p-6 bg-gradient-to-r from-blue-900/20 via-indigo-900/20 to-purple-900/20 border border-blue-200 dark:border-blue-900/40 rounded-2xl flex items-center justify-between">
          <div>
            <span className="inline-block px-2.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300 text-xs font-semibold uppercase tracking-wider mb-2">
              Milestone 9 Active
            </span>
            <h4 className="text-base font-bold text-gray-900 dark:text-white">
              Analytics, AI Predictions &amp; Exportable Reports
            </h4>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              End-to-end analytical dashboards, deterministic forecasting engines, and asynchronous multi-format reporting with CSV, Excel, and PDF exports.
            </p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
