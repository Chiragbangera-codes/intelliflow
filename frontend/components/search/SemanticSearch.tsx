"use client";

/**
 * SemanticSearch — Hybrid AI Document Search component (Phase 13).
 *
 * Phase 13 improvements over Phase 2:
 *   - Now calls hybrid search endpoint (semantic + lexical + RRF)
 *   - match_type badge per result (hybrid / semantic / lexical)
 *   - RRF score displayed alongside similarity
 *   - score field shown with label when present
 *   - colour band includes n/a state for lexical-only results (no similarity)
 *   - "View Source" navigates to /documents for the source document
 *
 * Security: RBAC is entirely server-side. This component never sends
 * owner IDs, chunk IDs, or any RBAC parameter — only the query text.
 */

import React, { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { semanticSearch } from "@/services/search.service";
import type { SearchResult } from "@/types";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

// Match type badge colours
const MATCH_STYLES: Record<string, string> = {
  hybrid: "bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300",
  semantic: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300",
  lexical: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300",
};

interface ResultCardProps {
  result: SearchResult & { score?: number | null; match_type?: string | null };
  rank: number;
}

function MatchTypeBadge({ matchType }: { matchType?: string | null }) {
  if (!matchType) return null;
  const cls = MATCH_STYLES[matchType] ?? "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400";
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${cls}`}>
      {matchType}
    </span>
  );
}

function ResultCard({ result, rank }: ResultCardProps) {
  const similarityPct =
    result.similarity != null ? Math.round(result.similarity * 100) : null;

  // Colour band for similarity badge
  const badgeClass =
    similarityPct == null
      ? "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
      : similarityPct >= 80
        ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300"
        : similarityPct >= 55
          ? "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300"
          : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400";

  return (
    <div
      className={`
        group relative p-5 rounded-xl border bg-white dark:bg-gray-900
        border-gray-200 dark:border-gray-800
        hover:border-indigo-400 dark:hover:border-indigo-600
        hover:shadow-md dark:hover:shadow-indigo-900/20
        transition-all duration-200
      `}
    >
      {/* Rank pill */}
      <span
        className="
          absolute -top-2.5 -left-2.5 w-6 h-6 rounded-full flex items-center
          justify-center text-[10px] font-bold
          bg-indigo-600 text-white shadow-sm
        "
      >
        {rank}
      </span>

      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
            {result.document_name}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Chunk {result.chunk_number}
            {result.file_type ? ` · ${result.file_type}` : ""}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          {/* match_type badge (Phase 13) */}
          <MatchTypeBadge matchType={(result as ResultCardProps["result"]).match_type} />
          {/* Similarity badge */}
          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${badgeClass}`}>
            {similarityPct != null ? `${similarityPct}% match` : "keyword match"}
          </span>
        </div>
      </div>

      {/* Content excerpt */}
      <p
        className="
          text-sm text-gray-700 dark:text-gray-300 leading-relaxed
          line-clamp-4 mb-4
        "
      >
        {result.content}
      </p>

      {/* Footer row: scores + view source */}
      <div className="flex items-center justify-between gap-3 pt-3 border-t border-gray-100 dark:border-gray-800 flex-wrap gap-y-1">
        <div className="flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500 flex-wrap">
          {result.distance != null && (
            <span title="FAISS L2 distance — lower means more similar">
              Distance:{" "}
              <span className="font-mono text-gray-600 dark:text-gray-400">
                {result.distance.toFixed(4)}
              </span>
            </span>
          )}
          {result.similarity != null && (
            <span title="Similarity = 1/(1+distance). Range 0–100%. Higher = more similar.">
              Similarity:{" "}
              <span className="font-mono text-gray-600 dark:text-gray-400">
                {result.similarity.toFixed(4)}
              </span>
            </span>
          )}
          {/* RRF/reranker score (Phase 13) */}
          {(result as ResultCardProps["result"]).score != null && (
            <span title="Reciprocal Rank Fusion (or reranker) score — higher is more relevant">
              Score:{" "}
              <span className="font-mono text-gray-600 dark:text-gray-400">
                {((result as ResultCardProps["result"]).score as number).toFixed(5)}
              </span>
            </span>
          )}
        </div>

        <Link
          href="/documents"
          className="
            inline-flex items-center gap-1.5 text-xs font-medium
            text-indigo-600 dark:text-indigo-400
            hover:text-indigo-800 dark:hover:text-indigo-300
            transition-colors
          "
          title={`Open documents — search for "${result.document_name}"`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
          View Source
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ query }: { query: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-14 h-14 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-4">
        <svg className="w-7 h-7 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
        No relevant documents found.
      </p>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 max-w-xs">
        Try a different question or search phrase.
      </p>
      {query && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 font-mono truncate max-w-xs">
          &ldquo;{query}&rdquo;
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800">
      <svg className="w-4 h-4 mt-0.5 shrink-0 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <p className="text-sm text-rose-700 dark:text-rose-300">{message}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface SemanticSearchProps {
  /** Default top_k value (1–20). */
  defaultTopK?: number;
  /** If true, renders as a compact inline panel. */
  compact?: boolean;
}

export function SemanticSearch({
  defaultTopK = 5,
  compact = false,
}: SemanticSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<(SearchResult & { score?: number | null; match_type?: string | null })[] | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSearch = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    setResults(null);
    setLastQuery(trimmed);

    try {
      const resp = await semanticSearch({ query: trimmed, top_k: defaultTopK });
      if (resp.success) {
        setResults(resp.data.results as typeof results);
      } else {
        setError("Search failed. Please try again.");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
      if (msg.toLowerCase().includes("network")) {
        setError("Network error. Please check your connection and try again.");
      } else if (msg.includes("422")) {
        setError("Invalid query. Please enter at least 2 characters.");
      } else {
        setError("Search is temporarily unavailable. Please try again later.");
      }
    } finally {
      setLoading(false);
    }
  }, [query, loading, defaultTopK]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSearch();
    }
  };

  const hasResults = results !== null && results.length > 0;
  const hasNoResults = results !== null && results.length === 0;

  // Count match types for summary
  const hybridCount = results?.filter((r) => r.match_type === "hybrid").length ?? 0;
  const semanticCount = results?.filter((r) => r.match_type === "semantic").length ?? 0;
  const lexicalCount = results?.filter((r) => r.match_type === "lexical").length ?? 0;

  return (
    <div className={compact ? "space-y-4" : "space-y-5"}>
      {/* Search input row */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          {/* Search icon */}
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none">
            {loading ? (
              <svg className="w-4 h-4 text-indigo-500 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            )}
          </span>

          <input
            ref={inputRef}
            id="semantic-search-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search with keywords or natural language…"
            disabled={loading}
            maxLength={1000}
            className="
              w-full pl-10 pr-4 py-2.5 text-sm
              bg-white dark:bg-gray-900
              border border-gray-200 dark:border-gray-700
              rounded-xl shadow-sm
              text-gray-900 dark:text-white
              placeholder-gray-400 dark:placeholder-gray-500
              focus:outline-none focus:ring-2 focus:ring-indigo-500/50
              focus:border-indigo-400 dark:focus:border-indigo-600
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-all duration-150
            "
            aria-label="Hybrid search query"
            aria-describedby="search-hint"
          />
        </div>

        <button
          id="semantic-search-button"
          type="button"
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="
            px-5 py-2.5 text-sm font-semibold rounded-xl
            bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800
            disabled:opacity-50 disabled:cursor-not-allowed
            text-white shadow-sm
            transition-all duration-150
            whitespace-nowrap
          "
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {/* Hint text */}
      {!hasResults && !hasNoResults && !error && !loading && (
        <p id="search-hint" className="text-xs text-gray-400 dark:text-gray-500">
          Hybrid search combines semantic understanding with keyword matching.
          Example: &ldquo;What does the engineering doc say about FAISS?&rdquo;
        </p>
      )}

      {/* Error */}
      {error && <ErrorState message={error} />}

      {/* Results */}
      {hasResults && (
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {results!.length} result{results!.length !== 1 ? "s" : ""} for{" "}
              <span className="font-semibold text-gray-700 dark:text-gray-200">
                &ldquo;{lastQuery}&rdquo;
              </span>
            </p>
            {/* Match type summary (Phase 13) */}
            <div className="flex items-center gap-1.5">
              {hybridCount > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300">
                  {hybridCount} hybrid
                </span>
              )}
              {semanticCount > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">
                  {semanticCount} semantic
                </span>
              )}
              {lexicalCount > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300">
                  {lexicalCount} lexical
                </span>
              )}
            </div>
          </div>
          <div className="space-y-3">
            {results!.map((r, i) => (
              <ResultCard key={r.chunk_id} result={r} rank={i + 1} />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {hasNoResults && <EmptyState query={lastQuery} />}
    </div>
  );
}

export default SemanticSearch;
