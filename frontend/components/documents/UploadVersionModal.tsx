"use client";

import React, { useRef, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { uploadDocumentVersion } from "@/services/document.service";
import type { EnterpriseDocument } from "@/types";

interface UploadVersionModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: EnterpriseDocument | null;
  onSuccess?: () => void;
}

export function UploadVersionModal({
  isOpen,
  onClose,
  document: doc,
  onSuccess,
}: UploadVersionModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [changeSummary, setChangeSummary] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!doc || !file) return;

    try {
      setUploading(true);
      setError(null);
      await uploadDocumentVersion(
        doc.id,
        file,
        changeSummary || `Version ${(doc.version_count || 1) + 1}`,
        (p) => setProgress(p),
      );
      setFile(null);
      setChangeSummary("");
      setProgress(null);
      onSuccess?.();
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to upload new version.";
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  if (!doc) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Upload New Version — ${doc.title || doc.file_name}`}>
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-lg">
            {error}
          </div>
        )}

        <div className="text-xs text-slate-400">
          Uploading a new version increments the document revision to{" "}
          <strong className="text-blue-400 font-semibold">Version {(doc.version_count || 1) + 1}</strong>.
          Historical versions are preserved immutably and remain accessible in Version History.
        </div>

        {/* Drop Area */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleFileDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition ${
            isDragOver
              ? "border-blue-500 bg-blue-500/10"
              : "border-slate-700 hover:border-slate-600 bg-slate-900/40"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.[0]) setFile(e.target.files[0]);
            }}
          />
          {file ? (
            <div className="space-y-1">
              <div className="text-sm font-semibold text-emerald-400">{file.name}</div>
              <div className="text-xs text-slate-400">
                {(file.size / (1024 * 1024)).toFixed(2)} MB • Ready to upload
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-slate-300 text-sm font-medium">
                Drag & drop replacement file here, or click to browse
              </div>
              <div className="text-xs text-slate-500">Supports PDF, DOCX, XLSX, PNG, JPG (Max 100MB)</div>
            </div>
          )}
        </div>

        {/* Change summary */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">
            Change Summary / Version Notes (Optional)
          </label>
          <input
            type="text"
            value={changeSummary}
            onChange={(e) => setChangeSummary(e.target.value)}
            placeholder="e.g., Updated clause 4.2 based on legal review"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Progress bar */}
        {uploading && progress !== null && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-slate-400">
              <span>Uploading revision...</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div
                className="bg-blue-600 h-full transition-all duration-200"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={uploading || !file}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium flex items-center gap-2 transition"
          >
            {uploading ? <LoadingSpinner size="sm" /> : "Upload Revision"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
