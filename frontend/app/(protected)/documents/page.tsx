"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { ExtractedTextViewerModal } from "@/components/documents/ExtractedTextViewerModal";
import { useAuthStore } from "@/store/auth.store";
import {
  getDocuments,
  uploadDocument,
  downloadDocument,
  updateDocument,
  deleteDocument,
} from "@/services/document.service";
import { startOCR, getOCRJobStatus } from "@/services/ocr.service";
import type {
  Document,
  DocumentQueryParams,
  DocumentSortField,
  DocumentStatus,
  PaginationMeta,
} from "@/types";

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"];
const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB

export default function DocumentsPage() {
  const { user } = useAuthStore();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [meta, setMeta] = useState<PaginationMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Search & Filter State
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "all">("all");
  const [sortField, setSortField] = useState<DocumentSortField>("-created_at");
  const [currentPage, setCurrentPage] = useState(1);

  // Upload Modal & State
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Details & Action Modals State
  const [detailsDoc, setDetailsDoc] = useState<Document | null>(null);
  const [textViewerDoc, setTextViewerDoc] = useState<Document | null>(null);
  const [editDoc, setEditDoc] = useState<Document | null>(null);
  const [deleteDoc, setDeleteDoc] = useState<Document | null>(null);
  const [editFileName, setEditFileName] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [copiedHash, setCopiedHash] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // OCR Processing state tracking & active polling timers
  const [processingOcrIds, setProcessingOcrIds] = useState<Record<string, boolean>>({});
  const pollTimersRef = useRef<Record<string, NodeJS.Timeout>>({});

  const canManageAll = user?.role === "admin" || user?.role === "hr";

  // Cleanup polling timers on unmount
  useEffect(() => {
    const activeTimers = pollTimersRef.current;
    return () => {
      Object.values(activeTimers).forEach((timer) => clearInterval(timer));
    };
  }, []);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setCurrentPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Refresh data helper
  const refreshDocuments = useCallback(
    async (page: number = currentPage) => {
      try {
        setLoading(true);
        setError(null);
        const params: DocumentQueryParams = {
          page,
          page_size: 15,
          search: debouncedSearch,
          status: statusFilter,
          sort: sortField,
        };
        const res = await getDocuments(params);
        if (res.success) {
          setDocuments(res.data);
          if (res.meta) setMeta(res.meta);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to load documents";
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [currentPage, debouncedSearch, statusFilter, sortField],
  );

  useEffect(() => {
    let isSubscribed = true;
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);
        const params: DocumentQueryParams = {
          page: currentPage,
          page_size: 15,
          search: debouncedSearch,
          status: statusFilter,
          sort: sortField,
        };
        const res = await getDocuments(params);
        if (isSubscribed && res.success) {
          setDocuments(res.data);
          if (res.meta) setMeta(res.meta);
        }
      } catch (err: unknown) {
        if (isSubscribed) {
          const msg = err instanceof Error ? err.message : "Failed to load documents";
          setError(msg);
        }
      } finally {
        if (isSubscribed) {
          setLoading(false);
        }
      }
    }
    fetchData();
    return () => {
      isSubscribed = false;
    };
  }, [currentPage, debouncedSearch, statusFilter, sortField]);

  // File size formatter
  const formatFileSize = (bytes?: number | null) => {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  // Status variant mapping
  const getStatusVariant = (status: string) => {
    switch (status) {
      case "processed":
      case "completed":
        return "success";
      case "processing":
        return "warning";
      case "failed":
        return "danger";
      case "skipped":
        return "neutral";
      default:
        return "info";
    }
  };

  // File icon generator
  const renderFileIcon = (fileName: string, type?: string | null) => {
    const ext = fileName.slice(fileName.lastIndexOf(".")).toLowerCase();
    if (ext === ".pdf" || type?.includes("pdf")) {
      return (
        <div className="w-9 h-9 rounded-xl bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800/60 flex items-center justify-center text-rose-600 dark:text-rose-400 shrink-0">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
        </div>
      );
    }
    if (ext === ".docx" || type?.includes("word")) {
      return (
        <div className="w-9 h-9 rounded-xl bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800/60 flex items-center justify-center text-blue-600 dark:text-blue-400 shrink-0">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
      );
    }
    if (ext === ".xlsx" || type?.includes("sheet") || type?.includes("excel")) {
      return (
        <div className="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-center text-emerald-600 dark:text-emerald-400 shrink-0">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
      );
    }
    return (
      <div className="w-9 h-9 rounded-xl bg-purple-50 dark:bg-purple-950/60 border border-purple-200 dark:border-purple-800/60 flex items-center justify-center text-purple-600 dark:text-purple-400 shrink-0">
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>
    );
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (file: File) => {
    setUploadError(null);
    if (!file || file.size === 0) {
      setUploadError("Cannot upload an empty file (0 bytes).");
      setSelectedFile(null);
      return;
    }
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setUploadError(
        `Unsupported format (${ext}). Allowed formats: ${ALLOWED_EXTENSIONS.join(", ")}`,
      );
      setSelectedFile(null);
      return;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setUploadError("File exceeds the maximum limit of 25 MB.");
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  };

  const handleUploadSubmit = async () => {
    if (!selectedFile) return;
    try {
      setUploading(true);
      setUploadProgress(0);
      setUploadError(null);

      await uploadDocument(selectedFile, (progress) => {
        setUploadProgress(progress);
      });

      setSuccessMessage(`Successfully uploaded "${selectedFile.name}"`);
      setSelectedFile(null);
      setUploadProgress(null);
      setIsUploadModalOpen(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      refreshDocuments(1);
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to upload document";
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  };

  // Download handler
  const handleDownload = async (doc: Document) => {
    try {
      setDownloadingId(doc.id);
      await downloadDocument(doc.id, doc.file_name);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to download document";
      alert(msg);
    } finally {
      setDownloadingId(null);
    }
  };

  // OCR Trigger & Polling Handler (Milestone 6)
  const handleTriggerOCR = async (doc: Document) => {
    try {
      setProcessingOcrIds((prev) => ({ ...prev, [doc.id]: true }));
      const res = await startOCR(doc.id);
      if (res.success && res.data) {
        const jobId = res.data.job_id;

        // Update local document status
        setDocuments((prev) =>
          prev.map((d) => (d.id === doc.id ? { ...d, ocr_status: "processing" } : d)),
        );
        if (detailsDoc?.id === doc.id) {
          setDetailsDoc((d) => (d ? { ...d, ocr_status: "processing" } : null));
        }

        // Poll Celery job status every 1.5s
        const interval = setInterval(async () => {
          try {
            const statusRes = await getOCRJobStatus(jobId);
            if (statusRes.success && statusRes.data) {
              const currentStatus = statusRes.data.status;
              if (currentStatus === "COMPLETED") {
                clearInterval(interval);
                delete pollTimersRef.current[doc.id];
                setProcessingOcrIds((prev) => {
                  const next = { ...prev };
                  delete next[doc.id];
                  return next;
                });
                setDocuments((prev) =>
                  prev.map((d) => (d.id === doc.id ? { ...d, ocr_status: "completed" } : d)),
                );
                if (detailsDoc?.id === doc.id) {
                  setDetailsDoc((d) => (d ? { ...d, ocr_status: "completed" } : null));
                }
                setSuccessMessage(`OCR processing completed for "${doc.file_name}"`);
                setTimeout(() => setSuccessMessage(null), 4000);
              } else if (currentStatus === "FAILED") {
                clearInterval(interval);
                delete pollTimersRef.current[doc.id];
                setProcessingOcrIds((prev) => {
                  const next = { ...prev };
                  delete next[doc.id];
                  return next;
                });
                setDocuments((prev) =>
                  prev.map((d) => (d.id === doc.id ? { ...d, ocr_status: "failed" } : d)),
                );
                if (detailsDoc?.id === doc.id) {
                  setDetailsDoc((d) => (d ? { ...d, ocr_status: "failed" } : null));
                }
              }
            }
          } catch {
            clearInterval(interval);
            delete pollTimersRef.current[doc.id];
            setProcessingOcrIds((prev) => {
              const next = { ...prev };
              delete next[doc.id];
              return next;
            });
          }
        }, 1500);

        pollTimersRef.current[doc.id] = interval;
      }
    } catch (err: unknown) {
      setProcessingOcrIds((prev) => {
        const next = { ...prev };
        delete next[doc.id];
        return next;
      });
      const msg = err instanceof Error ? err.message : "Failed to trigger OCR processing";
      alert(msg);
    }
  };

  // Edit metadata handler
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editDoc || !editFileName.trim()) return;

    try {
      setActionLoading(true);
      await updateDocument(editDoc.id, {
        file_name: editFileName.trim(),
      });
      setEditDoc(null);
      refreshDocuments(currentPage);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update metadata";
      alert(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Delete handler
  const handleDeleteConfirm = async () => {
    if (!deleteDoc) return;
    try {
      setActionLoading(true);
      await deleteDocument(deleteDoc.id);
      setDeleteDoc(null);
      refreshDocuments(currentPage);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete document";
      alert(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Copy hash helper
  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  return (
    <DashboardLayout
      title="Document Management & OCR Intelligence"
      description="Upload documents, execute automated text extraction, search contents, and inspect structured data chunks."
    >
      <div className="space-y-6">
        {/* Top Actions & Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white tracking-tight">
              All Documents
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Secure multi-format repository with automated OCR processing
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setUploadError(null);
              setSelectedFile(null);
              setUploadProgress(null);
              setIsUploadModalOpen(true);
            }}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 self-start sm:self-auto"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <span>Upload Document</span>
          </button>
        </div>

        {/* Success Alert Banner */}
        {successMessage && (
          <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-sm flex items-center justify-between animate-fadeIn">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>{successMessage}</span>
            </div>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-700 hover:text-emerald-900 dark:text-emerald-400">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Filter, Search & Sort Bar */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-4 shadow-sm space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            {/* Search Input */}
            <div className="relative flex-1">
              <svg className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search documents by file name..."
                className="w-full pl-10 pr-10 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>

            {/* Sorting Dropdown */}
            <div className="flex items-center gap-2 shrink-0">
              <label className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Sort By:
              </label>
              <select
                value={sortField}
                onChange={(e) => setSortField(e.target.value as DocumentSortField)}
                className="px-3 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-xs font-medium text-gray-700 dark:text-gray-300 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              >
                <option value="-created_at">Newest First</option>
                <option value="created_at">Oldest First</option>
                <option value="file_name">Name (A-Z)</option>
                <option value="-file_name">Name (Z-A)</option>
                <option value="file_size">Size (Small to Large)</option>
                <option value="-file_size">Size (Large to Small)</option>
              </select>
            </div>
          </div>

          {/* Status Filter Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pt-1">
            <span className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mr-1">
              Status:
            </span>
            {(["all", "pending", "processing", "processed", "failed"] as const).map((st) => (
              <button
                key={st}
                onClick={() => {
                  setStatusFilter(st);
                  setCurrentPage(1);
                }}
                className={`px-3 py-1 text-xs font-medium rounded-lg capitalize transition-all ${
                  statusFilter === st
                    ? "bg-blue-600 text-white shadow-xs"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        {/* Document Table / List */}
        {loading ? (
          <LoadingSpinner message="Loading document repository..." />
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm">
            {error}
          </div>
        ) : documents.length === 0 ? (
          <EmptyState
            title="No documents found"
            description={
              search || statusFilter !== "all"
                ? "No document records match your active search or status filter."
                : "Upload your first file to get started with document intelligence."
            }
          />
        ) : (
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800/60 border-b border-gray-200 dark:border-gray-800 text-gray-500 dark:text-gray-400 text-xs font-semibold uppercase tracking-wider">
                  <tr>
                    <th className="px-6 py-4">File Name</th>
                    <th className="px-6 py-4">Type</th>
                    <th className="px-6 py-4">Size</th>
                    <th className="px-6 py-4">Status</th>
                    <th className="px-6 py-4">OCR State</th>
                    <th className="px-6 py-4">Uploaded</th>
                    <th className="px-6 py-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {documents.map((doc) => {
                    const canEdit = canManageAll || user?.id === doc.owner_id;
                    const isDownloading = downloadingId === doc.id;
                    const isOcrProcessing =
                      doc.ocr_status === "processing" || !!processingOcrIds[doc.id];
                    const isOcrCompleted = doc.ocr_status === "completed";

                    return (
                      <tr
                        key={doc.id}
                        className="hover:bg-gray-50/50 dark:hover:bg-gray-800/40 transition-colors group"
                      >
                        <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                          <div className="flex items-center gap-3">
                            {renderFileIcon(doc.file_name, doc.file_type)}
                            <div className="truncate max-w-xs">
                              <span className="font-semibold block truncate" title={doc.file_name}>
                                {doc.file_name}
                              </span>
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                {doc.file_type || "document"}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-xs font-medium text-gray-600 dark:text-gray-300 uppercase">
                          {doc.file_name.slice(doc.file_name.lastIndexOf(".") + 1) || "DOC"}
                        </td>
                        <td className="px-6 py-4 text-xs font-mono text-gray-500 dark:text-gray-400">
                          {formatFileSize(doc.file_size)}
                        </td>
                        <td className="px-6 py-4">
                          <Badge variant={getStatusVariant(doc.status)} size="sm">
                            {doc.status}
                          </Badge>
                        </td>
                        <td className="px-6 py-4">
                          <Badge variant={getStatusVariant(doc.ocr_status)} size="sm">
                            {doc.ocr_status}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 text-xs text-gray-500 dark:text-gray-400">
                          {new Date(doc.created_at).toLocaleDateString(undefined, {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          })}
                        </td>
                        <td className="px-6 py-4 text-right space-x-1.5 shrink-0">
                          {/* OCR Actions (Milestone 6 & 6.1) */}
                          {isOcrCompleted ? (
                            <button
                              onClick={() => setTextViewerDoc(doc)}
                              className="px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/50 hover:bg-emerald-100 dark:hover:bg-emerald-900/50 rounded-lg transition-colors inline-flex items-center gap-1 border border-emerald-200 dark:border-emerald-800"
                              title="View extracted text & chunks"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              <span>View Text</span>
                            </button>
                          ) : isOcrProcessing ? (
                            <span className="px-2.5 py-1 text-xs font-medium text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 rounded-lg inline-flex items-center gap-1.5">
                              <div className="w-3 h-3 border-2 border-amber-600 border-t-transparent rounded-full animate-spin"></div>
                              <span>Extracting...</span>
                            </span>
                          ) : (
                            <button
                              onClick={() => handleTriggerOCR(doc)}
                              className="px-2.5 py-1 text-xs font-semibold text-blue-700 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/50 hover:bg-blue-100 dark:hover:bg-blue-900/50 rounded-lg transition-colors inline-flex items-center gap-1 border border-blue-200 dark:border-blue-800"
                              title="Trigger OCR & Text Extraction"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                              </svg>
                              <span>Extract Text</span>
                            </button>
                          )}

                          <button
                            onClick={() => setDetailsDoc(doc)}
                            className="px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                            title="View full metadata"
                          >
                            Details
                          </button>
                          <button
                            onClick={() => handleDownload(doc)}
                            disabled={isDownloading}
                            className="px-2.5 py-1 text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40 rounded-lg transition-colors inline-flex items-center gap-1"
                            title="Download file"
                          >
                            {isDownloading ? (
                              <div className="w-3 h-3 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                            ) : (
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                              </svg>
                            )}
                            <span>Download</span>
                          </button>
                          {canEdit && (
                            <>
                              <button
                                onClick={() => {
                                  setEditDoc(doc);
                                  setEditFileName(doc.file_name);
                                }}
                                className="px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-blue-600 dark:text-gray-400 hover:bg-blue-50 dark:hover:bg-blue-950/40 rounded-lg transition-colors"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => setDeleteDoc(doc)}
                                className="px-2.5 py-1 text-xs font-medium text-rose-600 hover:text-rose-700 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-lg transition-colors"
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {meta && meta.total_pages > 1 && (
              <div className="p-4 border-t border-gray-100 dark:divide-gray-800 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span>
                  Showing page {meta.page} of {meta.total_pages} ({meta.total_items} total)
                </span>
                <div className="flex items-center gap-2">
                  <button
                    disabled={meta.page <= 1}
                    onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                    className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg font-medium transition-colors disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    disabled={meta.page >= meta.total_pages}
                    onClick={() => setCurrentPage((p) => p + 1)}
                    className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg font-medium transition-colors disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Upload Document Modal (Milestone 6.1) */}
        <Modal
          isOpen={isUploadModalOpen}
          onClose={() => {
            if (!uploading) {
              setIsUploadModalOpen(false);
              setSelectedFile(null);
              setUploadProgress(null);
              setUploadError(null);
            }
          }}
          title="Upload Document"
          maxWidth="lg"
        >
          <div className="space-y-4">
            {/* Drag-and-Drop Area */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all ${
                isDragOver
                  ? "border-blue-500 bg-blue-50/50 dark:bg-blue-950/30 scale-[0.99]"
                  : "border-gray-300 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-600 bg-gray-50/50 dark:bg-gray-900/50"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg"
                onChange={handleFileChange}
                className="hidden"
              />
              <div className="flex flex-col items-center justify-center space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-blue-100 dark:bg-blue-950 flex items-center justify-center text-blue-600 dark:text-blue-400 shadow-inner">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">
                    Drag and drop file here, or{" "}
                    <span className="text-blue-600 dark:text-blue-400 underline">browse</span>
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Select a document from your computer to store & extract
                  </p>
                </div>
              </div>
            </div>

            {/* Supported formats & max size notice */}
            <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-xl border border-gray-100 dark:border-gray-800 flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Formats:
                </span>
                {["PDF", "DOCX", "XLSX", "PNG", "JPG", "JPEG"].map((fmt) => (
                  <span
                    key={fmt}
                    className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-mono rounded text-[10px]"
                  >
                    {fmt}
                  </span>
                ))}
              </div>
              <span className="text-gray-400 dark:text-gray-500 font-medium">
                Max 25 MB
              </span>
            </div>

            {/* Selected File Card */}
            {selectedFile && (
              <div className="p-3.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800/60 flex items-center justify-between animate-fadeIn">
                <div className="flex items-center gap-3">
                  {renderFileIcon(selectedFile.name, selectedFile.type)}
                  <div className="truncate max-w-xs">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {formatFileSize(selectedFile.size)} &bull; {selectedFile.type || "Document"}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setSelectedFile(null);
                    setUploadProgress(null);
                    setUploadError(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  disabled={uploading}
                  className="p-1.5 text-gray-400 hover:text-rose-600 dark:hover:text-rose-400 rounded-lg transition-colors"
                  title="Remove selected file"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {/* Upload Progress Bar */}
            {uploadProgress !== null && (
              <div className="space-y-1.5 animate-fadeIn">
                <div className="flex justify-between text-xs font-medium text-gray-700 dark:text-gray-300">
                  <span>Streaming file to server storage...</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${uploadProgress}%` }}
                  ></div>
                </div>
              </div>
            )}

            {/* Upload Error Alert */}
            {uploadError && (
              <div className="p-3 text-xs bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 rounded-xl border border-rose-200 dark:border-rose-800 flex items-center gap-2 animate-fadeIn">
                <svg className="w-4 h-4 text-rose-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{uploadError}</span>
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setIsUploadModalOpen(false);
                  setSelectedFile(null);
                  setUploadProgress(null);
                  setUploadError(null);
                }}
                disabled={uploading}
                className="px-4 py-2 text-xs font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleUploadSubmit}
                disabled={!selectedFile || uploading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-all disabled:opacity-50 flex items-center gap-2"
              >
                {uploading ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Uploading...</span>
                  </>
                ) : (
                  <span>Upload Document</span>
                )}
              </button>
            </div>
          </div>
        </Modal>

        {/* Document Details Modal */}
        <Modal
          isOpen={!!detailsDoc}
          onClose={() => setDetailsDoc(null)}
          title="Document Metadata & OCR Verification"
        >
          {detailsDoc && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-4 bg-gray-50 dark:bg-gray-800/60 rounded-xl">
                {renderFileIcon(detailsDoc.file_name, detailsDoc.file_type)}
                <div className="truncate">
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                    {detailsDoc.file_name}
                  </h4>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {formatFileSize(detailsDoc.file_size)} &bull; {detailsDoc.file_type || "application/octet-stream"}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-xl border border-gray-100 dark:border-gray-800">
                  <span className="text-gray-400 dark:text-gray-500 block mb-1">Status</span>
                  <Badge variant={getStatusVariant(detailsDoc.status)} size="sm">
                    {detailsDoc.status}
                  </Badge>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-xl border border-gray-100 dark:border-gray-800">
                  <span className="text-gray-400 dark:text-gray-500 block mb-1">OCR Pipeline</span>
                  <Badge variant={getStatusVariant(detailsDoc.ocr_status)} size="sm">
                    {detailsDoc.ocr_status}
                  </Badge>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-xl border border-gray-100 dark:border-gray-800">
                  <span className="text-gray-400 dark:text-gray-500 block mb-1">Created At</span>
                  <span className="font-semibold text-gray-900 dark:text-white">
                    {new Date(detailsDoc.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-gray-800/40 rounded-xl border border-gray-100 dark:border-gray-800">
                  <span className="text-gray-400 dark:text-gray-500 block mb-1">Owner ID</span>
                  <span className="font-mono text-gray-700 dark:text-gray-300 truncate block" title={detailsDoc.owner_id}>
                    {detailsDoc.owner_id}
                  </span>
                </div>
              </div>

              {/* SHA-256 Checksum with Copy */}
              <div className="p-3.5 bg-gray-50 dark:bg-gray-800/40 rounded-xl border border-gray-100 dark:border-gray-800">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    SHA-256 Integrity Checksum
                  </span>
                  {detailsDoc.checksum && (
                    <button
                      type="button"
                      onClick={() => handleCopyHash(detailsDoc.checksum!)}
                      className="text-xs font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400 flex items-center gap-1"
                    >
                      {copiedHash ? (
                        <span>Copied!</span>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                          <span>Copy Hash</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
                <p className="font-mono text-xs text-gray-700 dark:text-gray-300 break-all bg-white dark:bg-gray-900 p-2 rounded-lg border border-gray-200 dark:border-gray-700 select-all">
                  {detailsDoc.checksum || "Checksum calculation pending"}
                </p>
              </div>

              <div className="flex flex-wrap justify-between items-center gap-2 pt-2">
                <div className="flex items-center gap-2">
                  {detailsDoc.ocr_status === "completed" ? (
                    <button
                      type="button"
                      onClick={() => {
                        const target = detailsDoc;
                        setDetailsDoc(null);
                        setTextViewerDoc(target);
                      }}
                      className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-xl shadow-sm transition-all flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span>View Extracted Text</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleTriggerOCR(detailsDoc)}
                      disabled={detailsDoc.ocr_status === "processing" || !!processingOcrIds[detailsDoc.id]}
                      className="px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-medium rounded-xl shadow-sm transition-all flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      <span>{detailsDoc.ocr_status === "processing" || !!processingOcrIds[detailsDoc.id] ? "OCR Running..." : "Run OCR Extraction"}</span>
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setDetailsDoc(null)}
                    className="px-3.5 py-2 text-xs font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl"
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDownload(detailsDoc)}
                    className="px-3.5 py-2 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-white text-xs font-semibold rounded-xl shadow-sm transition-all flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    <span>Download</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </Modal>

        {/* Extracted Text Viewer Modal (Milestone 6) */}
        <ExtractedTextViewerModal
          document={textViewerDoc}
          isOpen={!!textViewerDoc}
          onClose={() => setTextViewerDoc(null)}
        />

        {/* Edit Metadata Modal */}
        <Modal
          isOpen={!!editDoc}
          onClose={() => setEditDoc(null)}
          title="Edit Document Name"
        >
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                File Name *
              </label>
              <input
                type="text"
                required
                value={editFileName}
                onChange={(e) => setEditFileName(e.target.value)}
                className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setEditDoc(null)}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {actionLoading ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </form>
        </Modal>

        {/* Delete Confirmation Modal */}
        <Modal
          isOpen={!!deleteDoc}
          onClose={() => setDeleteDoc(null)}
          title="Confirm Soft-Delete"
        >
          <div className="space-y-4">
            <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
              Are you sure you want to delete{" "}
              <strong className="text-gray-900 dark:text-white font-semibold">
                &ldquo;{deleteDoc?.file_name}&rdquo;
              </strong>
              ?
            </p>
            <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-xl border border-amber-200 dark:border-amber-800">
              Per database retention compliance, this document will be soft-deleted. The action will be recorded in the audit trail.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setDeleteDoc(null)}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConfirm}
                disabled={actionLoading}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {actionLoading ? "Deleting..." : "Confirm Delete"}
              </button>
            </div>
          </div>
        </Modal>
      </div>
    </DashboardLayout>
  );
}
