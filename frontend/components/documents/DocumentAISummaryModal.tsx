"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { Badge } from "@/components/ui/Badge";
import { getDocumentAISummary } from "@/services/document.service";
import type { DocumentAISummaryResponse, EnterpriseDocument } from "@/types";

interface DocumentAISummaryModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: EnterpriseDocument | null;
}

export function DocumentAISummaryModal({
  isOpen,
  onClose,
  document: doc,
}: DocumentAISummaryModalProps) {
  const [summaryData, setSummaryData] = useState<DocumentAISummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!doc) return;
    try {
      setLoading(true);
      setError(null);
      const res = await getDocumentAISummary(doc.id);
      setSummaryData(res.data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to generate AI summary.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [doc]);

  useEffect(() => {
    if (!isOpen || !doc) return;
    fetchSummary();
  }, [isOpen, doc, fetchSummary]);

  if (!doc) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`AI Executive Summary — ${doc.title || doc.file_name}`}
    >
      <div className="space-y-6">
        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center space-y-4">
            <LoadingSpinner size="lg" />
            <div className="text-center space-y-1">
              <p className="text-sm font-medium text-slate-200">Analyzing document chunks...</p>
              <p className="text-xs text-slate-400">
                Extracting key facts, metrics, and obligations through grounded AI synthesis.
              </p>
            </div>
          </div>
        ) : error ? (
          <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-xl space-y-2">
            <div className="font-semibold">Unable to Generate Summary</div>
            <div className="text-xs">{error}</div>
            <button
              onClick={fetchSummary}
              className="mt-2 px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-xs rounded font-medium"
            >
              Retry
            </button>
          </div>
        ) : summaryData ? (
          <div className="space-y-6">
            {/* Header info */}
            <div className="flex items-center justify-between text-xs text-slate-400 bg-slate-900/50 p-3 rounded-lg border border-slate-800">
              <div className="flex items-center gap-2">
                <span>Version: <strong className="text-slate-200">v{doc.current_version_number || 1}</strong></span>
                <span>•</span>
                <span>Chunks Analyzed: <strong className="text-slate-200">{summaryData.chunks_used}</strong></span>
              </div>
              <Badge variant="primary" className="text-xs">
                Grounded LLM
              </Badge>
            </div>

            {/* Formatted Summary Content */}
            <div className="prose prose-invert max-w-none text-sm text-slate-200 leading-relaxed bg-slate-900/30 p-4 rounded-xl border border-slate-800 whitespace-pre-wrap">
              {summaryData.summary}
            </div>

            {/* Sources & Citations */}
            {summaryData.sources && summaryData.sources.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Cited Document Passages ({summaryData.sources.length})
                </h4>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {summaryData.sources.map((src, idx) => (
                    <div
                      key={src.chunk_id}
                      className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs space-y-1 hover:border-slate-700 transition"
                    >
                      <div className="flex items-center justify-between font-medium text-slate-400">
                        <span className="text-blue-400 font-semibold">Passage #{idx + 1} (Chunk {src.chunk_number})</span>
                      </div>
                      <div className="text-slate-300 italic line-clamp-3">
                        &ldquo;{src.content}&rdquo;
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
