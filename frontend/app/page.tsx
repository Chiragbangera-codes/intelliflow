"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth.store";
import Link from "next/link";

export default function HomePage() {
  const router = useRouter();
  const { isAuthenticated, isInitializing, initialize, user } = useAuthStore();

  useEffect(() => {
    initialize();
  }, [initialize]);

  if (isInitializing) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
        <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 bg-gradient-to-b from-white to-gray-50 dark:from-gray-950 dark:to-gray-900 text-gray-900 dark:text-white">
      <div className="max-w-xl text-center space-y-6">
        <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 text-blue-600 dark:text-blue-400 text-xs font-semibold uppercase tracking-wider">
          <span>Milestone 4: Core Application APIs & Dashboard</span>
        </div>

        <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">
          IntelliFlow AI
        </h1>

        <p className="text-lg text-gray-600 dark:text-gray-400">
          Enterprise SaaS platform combining AI, Workflow Automation, Document Intelligence, and Predictive Analytics.
        </p>

        {isAuthenticated && user ? (
          <div className="p-6 bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-lg text-left space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                Authenticated Session
              </h3>
              <span className="inline-block px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs font-mono font-semibold uppercase">
                {user.role}
              </span>
            </div>

            <div className="text-sm space-y-1.5 text-gray-600 dark:text-gray-300">
              <p>
                <span className="font-semibold">User:</span> {user.first_name}{" "}
                {user.last_name} ({user.email})
              </p>
              <p>
                <span className="font-semibold">Status:</span>{" "}
                <span className="inline-block px-2 py-0.5 rounded bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 text-xs font-mono">
                  {user.status}
                </span>
              </p>
            </div>

            <div className="pt-2 flex items-center gap-3">
              <Link
                href="/dashboard"
                className="flex-1 text-center px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-semibold shadow-sm transition-all"
              >
                Go to Dashboard
              </Link>
              <button
                onClick={() => {
                  useAuthStore.getState().clearAuth();
                  router.push("/login");
                }}
                className="px-4 py-2.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-xl text-sm font-medium transition-all"
              >
                Sign out
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center space-x-4">
            <Link
              href="/login"
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl shadow-lg shadow-blue-600/20 transition-all text-sm"
            >
              Sign In
            </Link>
            <Link
              href="/register"
              className="px-6 py-3 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-900 dark:text-white font-medium rounded-xl transition-all text-sm border border-gray-200 dark:border-gray-700"
            >
              Register Account
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}
