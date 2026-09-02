"use client";

import React, { useState } from "react";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import {
  bulkArchiveDocuments,
  bulkDeleteDocuments,
  bulkRestoreDocuments,
  bulkTagDocuments,
} from "@/services/document.service";
import type { BulkOperationResponse } from "@/types";

interface BulkActionsBarProps {
  selectedIds: string[];
  onClearSelection: () => void;
  onSuccess: (result: BulkOperationResponse) => void;
  onError: (msg: string) => void;
}

export function BulkActionsBar({
  selectedIds,
  onClearSelection,
  onSuccess,
  onError,
}: BulkActionsBarProps) {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [showTagModal, setShowTagModal] = useState(false);
  const [tagInput, setTagInput] = useState("");

  if (selectedIds.length === 0) return null;

  const handleArchive = async () => {
    try {
      setLoadingAction("archive");
      const res = await bulkArchiveDocuments(selectedIds);
      onSuccess(res.data);
      onClearSelection();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Bulk archive failed.");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRestore = async () => {
    try {
      setLoadingAction("restore");
      const res = await bulkRestoreDocuments(selectedIds);
      onSuccess(res.data);
      onClearSelection();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Bulk restore failed.");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete ${selectedIds.length} document(s)?`)) return;
    try {
      setLoadingAction("delete");
      const res = await bulkDeleteDocuments(selectedIds);
      onSuccess(res.data);
      onClearSelection();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Bulk delete failed.");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleApplyTags = async (e: React.FormEvent) => {
    e.preventDefault();
    const tags = tagInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (tags.length === 0) return;

    try {
      setLoadingAction("tag");
      const res = await bulkTagDocuments(selectedIds, tags, false);
      setShowTagModal(false);
      setTagInput("");
      onSuccess(res.data);
      onClearSelection();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Bulk tagging failed.");
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <>
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-slate-900/90 backdrop-blur-md border border-slate-700 shadow-2xl rounded-2xl px-5 py-3 flex items-center gap-4 text-sm animate-in fade-in slide-in-from-bottom-4 duration-200">
        <div className="flex items-center gap-2">
          <span className="w-6 h-6 rounded-full bg-blue-600 text-white font-semibold text-xs flex items-center justify-center">
            {selectedIds.length}
          </span>
          <span className="text-slate-300 font-medium hidden sm:inline">selected</span>
        </div>

        <div className="h-5 w-px bg-slate-700" />

        <div className="flex items-center gap-2">
          {/* Tag */}
          <button
            onClick={() => setShowTagModal(true)}
            disabled={!!loadingAction}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium flex items-center gap-1.5 transition"
          >
            Tag Batch
          </button>

          {/* Archive */}
          <button
            onClick={handleArchive}
            disabled={!!loadingAction}
            className="px-3 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-medium flex items-center gap-1.5 transition"
          >
            {loadingAction === "archive" ? <LoadingSpinner size="sm" /> : "Archive"}
          </button>

          {/* Restore */}
          <button
            onClick={handleRestore}
            disabled={!!loadingAction}
            className="px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-medium flex items-center gap-1.5 transition"
          >
            {loadingAction === "restore" ? <LoadingSpinner size="sm" /> : "Restore"}
          </button>

          {/* Delete */}
          <button
            onClick={handleDelete}
            disabled={!!loadingAction}
            className="px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 text-xs font-medium flex items-center gap-1.5 transition"
          >
            {loadingAction === "delete" ? <LoadingSpinner size="sm" /> : "Delete"}
          </button>
        </div>

        <div className="h-5 w-px bg-slate-700" />

        <button
          onClick={onClearSelection}
          className="text-xs text-slate-400 hover:text-slate-200 transition"
        >
          Deselect
        </button>
      </div>

      {/* Tag Modal */}
      {showTagModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <h3 className="text-base font-semibold text-slate-100">Add Tags to Batch</h3>
            <p className="text-xs text-slate-400">
              Enter comma-separated tags to append to the {selectedIds.length} selected documents.
            </p>
            <form onSubmit={handleApplyTags} className="space-y-4">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                placeholder="e.g. Q1-2026, compliance, audit"
                required
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowTagModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loadingAction === "tag"}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium flex items-center gap-2"
                >
                  {loadingAction === "tag" ? <LoadingSpinner size="sm" /> : "Apply Tags"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
