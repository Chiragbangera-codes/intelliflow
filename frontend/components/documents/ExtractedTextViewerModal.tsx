"use client";

import React, { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { getDocumentText } from "@/services/ocr.service";
import type { Document, DocumentTextResponse } from "@/types";

interface ExtractedTextViewerModalProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
}

export const ExtractedTextViewerModal: React.FC<ExtractedTextViewerModalProps> = ({
  document: doc,
  isOpen,
  onClose,
}) => {
  const [data, setData] = useState<DocumentTextResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"full" | "chunks">("full");
  const [searchQuery, setSearchQuery] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isOpen || !doc) return;

    let isMounted = true;
    async function fetchText() {
      if (!doc) return;
      try {
        setLoading(true);
        setError(null);
        const res = await getDocumentText(doc.id);
        if (isMounted && res.success) {
          setData(res.data);
        }
      } catch (err: unknown) {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : "Failed to load extracted text";
          setError(msg);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchText();
    return () => {
      isMounted = false;
    };
  }, [isOpen, doc]);

  const handleCopy = () => {
    if (!data?.text) return;
    navigator.clipboard.writeText(data.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filteredChunks = data?.chunks.filter((c) =>
    searchQuery.trim()
      ? c.content.toLowerCase().includes(searchQuery.toLowerCase())
      : true,
  ) || [];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Extracted Document Text & Chunks"
      maxWidth="3xl"
    >
      <div className="space-y-4 max-h-[78vh] flex flex-col">
        {/* Document Header Meta */}
        {doc && (
          <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-gray-50 dark:bg-gray-800/60 rounded-xl border border-gray-100 dark:border-gray-800 shrink-0">
            <div className="flex items-center gap-3 truncate">
              <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-950 flex items-center justify-center text-blue-600 dark:text-blue-400 shrink-0 font-bold text-xs">
                OCR
              </div>
              <div className="truncate">
                <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                  {doc.file_name}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {data ? `${data.total_chunks} Chunks • ${data.text.length.toLocaleString()} characters` : "Loading content..."}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={doc.ocr_status === "completed" ? "success" : "info"} size="sm">
                OCR: {doc.ocr_status}
              </Badge>
              {data?.text && (
                <button
                  onClick={handleCopy}
                  className="px-3 py-1.5 bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 border border-gray-200 dark:border-gray-600 text-xs font-semibold rounded-lg shadow-2xs transition-all flex items-center gap-1.5 text-gray-700 dark:text-gray-200"
                >
                  {copied ? (
                    <>
                      <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span>Copied!</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      <span>Copy Full Text</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        )}

        {/* View Switcher & Search Bar */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 shrink-0">
          <div className="flex items-center p-1 bg-gray-100 dark:bg-gray-800 rounded-xl">
            <button
              onClick={() => setActiveTab("full")}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                activeTab === "full"
                  ? "bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow-xs font-semibold"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
              }`}
            >
              Full Document Text
            </button>
            <button
              onClick={() => setActiveTab("chunks")}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                activeTab === "chunks"
                  ? "bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow-xs font-semibold"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
              }`}
            >
              Ordered Chunks ({data?.total_chunks || 0})
            </button>
          </div>

          <div className="relative flex-1 max-w-xs">
            <svg className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search in extracted content..."
              className="w-full pl-9 pr-3 py-1.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-xs focus:outline-hidden focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Content Container */}
        <div className="flex-1 overflow-y-auto min-h-[300px] border border-gray-200 dark:border-gray-800 rounded-xl bg-gray-50/50 dark:bg-gray-900/50 p-4">
          {loading ? (
            <div className="py-12">
              <LoadingSpinner message="Fetching extracted text chunks..." />
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
              {error}
            </div>
          ) : !data || data.total_chunks === 0 ? (
            <EmptyState
              title="No extracted text available"
              description={
                doc?.ocr_status === "processing"
                  ? "OCR extraction is currently in progress. Please check back shortly."
                  : doc?.ocr_status === "failed"
                  ? "OCR processing failed for this document. You can retry extracting text."
                  : "Click 'Extract Text' to run OCR and extract readable content from this document."
              }
            />
          ) : activeTab === "full" ? (
            <div className="space-y-2">
              <pre className="text-xs font-mono text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed select-text font-sans">
                {data.text}
              </pre>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredChunks.length === 0 ? (
                <p className="text-xs text-gray-500 text-center py-6">
                  No chunks match your search query &ldquo;{searchQuery}&rdquo;.
                </p>
              ) : (
                filteredChunks.map((chunk) => (
                  <div
                    key={chunk.id}
                    className="p-3.5 bg-white dark:bg-gray-800/80 rounded-xl border border-gray-200 dark:border-gray-700/80 shadow-2xs space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs text-gray-400">
                      <span className="font-semibold text-blue-600 dark:text-blue-400">
                        Chunk #{chunk.chunk_number}
                      </span>
                      <span>{chunk.content.length} chars</span>
                    </div>
                    <p className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                      {chunk.content}
                    </p>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end pt-2 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs font-semibold rounded-xl transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
};
