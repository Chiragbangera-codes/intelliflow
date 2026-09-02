"use client";

import { useEffect } from "react";
import Link from "next/link";

function AlertCircleIcon({ className = "w-6 h-6" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function RefreshCwIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

function HomeIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    </svg>
  );
}

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Route error boundary caught an error:", error);
  }, [error]);

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 text-center">
      <div className="w-16 h-16 bg-red-50 dark:bg-red-950/40 rounded-2xl flex items-center justify-center text-red-600 dark:text-red-400 mb-4 border border-red-200 dark:border-red-800/50 shadow-sm">
        <AlertCircleIcon className="w-8 h-8" />
      </div>

      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
        Application Error
      </h1>

      <p className="text-sm text-gray-600 dark:text-gray-400 max-w-md mb-6">
        An unexpected error occurred while loading this page. You can attempt to
        recover by refreshing the state or navigating home.
      </p>

      {error?.message && (
        <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-900 rounded-xl text-xs font-mono text-gray-700 dark:text-gray-300 max-w-lg overflow-x-auto text-left border border-gray-200 dark:border-gray-800">
          <div className="text-gray-400 mb-1">Error message:</div>
          <div>{error.message}</div>
          {error.digest && (
            <div className="mt-2 text-gray-400">
              Digest ID: <span className="text-gray-600 dark:text-gray-300">{error.digest}</span>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={() => reset()}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl bg-blue-600 hover:bg-blue-700 text-white transition-colors shadow-sm"
        >
          <RefreshCwIcon className="w-4 h-4" />
          Reload Page
        </button>

        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 transition-colors border border-gray-200 dark:border-gray-700"
        >
          <HomeIcon className="w-4 h-4" />
          Return to Dashboard
        </Link>
      </div>
    </div>
  );
}
