"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { ExtractedTextViewerModal } from "@/components/documents/ExtractedTextViewerModal";
import { ShareDocumentModal } from "@/components/documents/ShareDocumentModal";
import { UploadVersionModal } from "@/components/documents/UploadVersionModal";
import { BulkActionsBar } from "@/components/documents/BulkActionsBar";
import { DocumentAISummaryModal } from "@/components/documents/DocumentAISummaryModal";
import { DocumentAIChatModal } from "@/components/documents/DocumentAIChatModal";
import {
  getDocuments,
  uploadDocument,
  downloadDocument,
  deleteDocument,
  archiveDocument,
  restoreDocument,
} from "@/services/document.service";
import type {
  DocumentConfidentiality,
  DocumentLifecycleStatus,
  DocumentQueryParams,
  DocumentSortField,
  EnterpriseDocument,
  PaginationMeta,
} from "@/types";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<EnterpriseDocument[]>([]);
  const [meta, setMeta] = useState<PaginationMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Search & Filter State
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [lifecycleFilter, setLifecycleFilter] = useState<DocumentLifecycleStatus | "all">("all");
  const [confidentialityFilter, setConfidentialityFilter] = useState<DocumentConfidentiality | "all">("all");
  const [sharedWithMe, setSharedWithMe] = useState(false);
  const [sortField, setSortField] = useState<DocumentSortField>("-created_at");
  const [currentPage, setCurrentPage] = useState(1);

  // Multi-Selection State for Bulk Operations
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Modals & Action Targets
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadCategory, setUploadCategory] = useState("General");
  const [uploadConfidentiality, setUploadConfidentiality] = useState<DocumentConfidentiality>("internal");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Specific Feature Modals
  const [shareDoc, setShareDoc] = useState<EnterpriseDocument | null>(null);
  const [versionDoc, setVersionDoc] = useState<EnterpriseDocument | null>(null);
  const [summaryDoc, setSummaryDoc] = useState<EnterpriseDocument | null>(null);
  const [chatDoc, setChatDoc] = useState<EnterpriseDocument | null>(null);
  const [textViewerDoc, setTextViewerDoc] = useState<EnterpriseDocument | null>(null);
  const [deleteDoc, setDeleteDoc] = useState<EnterpriseDocument | null>(null);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setCurrentPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Fetch Documents
  const fetchDocuments = useCallback(
    async (page: number = currentPage) => {
      try {
        setLoading(true);
        setError(null);
        const params: DocumentQueryParams = {
          page,
          page_size: 15,
          search: debouncedSearch,
          lifecycle_status: lifecycleFilter,
          confidentiality: confidentialityFilter,
          shared_with_me: sharedWithMe ? true : undefined,
          sort: sortField,
        };
        const res = await getDocuments(params);
        setDocuments(res.data || []);
        if (res.meta) setMeta(res.meta);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to load documents.";
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [currentPage, debouncedSearch, lifecycleFilter, confidentialityFilter, sharedWithMe, sortField],
  );

  useEffect(() => {
    fetchDocuments(currentPage);
  }, [fetchDocuments, currentPage]);

  // Selection Handlers
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(documents.map((d) => d.id));
    } else {
      setSelectedIds([]);
    }
  };

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  // Upload Handler
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;

    try {
      setUploading(true);
      setUploadError(null);
      const parsedTags = uploadTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      await uploadDocument(uploadFile, {
        title: uploadTitle || uploadFile.name,
        category: uploadCategory,
        confidentiality: uploadConfidentiality,
        tags: parsedTags,
        onUploadProgress: (p) => setUploadProgress(p),
      });

      setSuccessMessage("Document uploaded successfully.");
      setIsUploadModalOpen(false);
      setUploadFile(null);
      setUploadTitle("");
      setUploadTags("");
      setUploadProgress(null);
      fetchDocuments(1);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed.";
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  };

  // Lifecycle Action Handlers
  const handleArchive = async (id: string) => {
    try {
      await archiveDocument(id);
      setSuccessMessage("Document archived.");
      fetchDocuments();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Archive failed.");
    }
  };

  const handleRestore = async (id: string) => {
    try {
      await restoreDocument(id);
      setSuccessMessage("Document restored to active state.");
      fetchDocuments();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Restore failed.");
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteDoc) return;
    try {
      await deleteDocument(deleteDoc.id);
      setSuccessMessage("Document deleted.");
      setDeleteDoc(null);
      fetchDocuments();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  // Helper formatting
  const getConfidentialityBadge = (conf: DocumentConfidentiality) => {
    switch (conf) {
      case "public":
        return <Badge variant="neutral" className="text-xs">Public</Badge>;
      case "internal":
        return <Badge variant="primary" className="text-xs">Internal</Badge>;
      case "confidential":
        return <Badge variant="warning" className="text-xs">Confidential</Badge>;
      case "restricted":
        return <Badge variant="danger" className="text-xs">Restricted</Badge>;
      default:
        return null;
    }
  };

  const getLifecycleBadge = (status: DocumentLifecycleStatus) => {
    switch (status) {
      case "active":
        return <Badge variant="success" className="text-xs">Active</Badge>;
      case "draft":
        return <Badge variant="neutral" className="text-xs">Draft</Badge>;
      case "archived":
        return <Badge variant="warning" className="text-xs">Archived</Badge>;
      case "expired":
        return <Badge variant="danger" className="text-xs">Expired</Badge>;
      case "deleted":
        return <Badge variant="danger" className="text-xs">Deleted</Badge>;
      default:
        return null;
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header banner */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Document Intelligence</h1>
            <p className="text-sm text-slate-400 mt-1">
              Enterprise document repository with immutable versioning, RBAC access grants, AI synthesis & audit trails.
            </p>
          </div>
          <button
            onClick={() => setIsUploadModalOpen(true)}
            className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 transition"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Upload Document
          </button>
        </div>

        {/* Success / Error Banners */}
        {successMessage && (
          <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm rounded-xl flex items-center justify-between">
            <span>{successMessage}</span>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-300 text-xs hover:underline">
              Dismiss
            </button>
          </div>
        )}
        {error && (
          <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-xl flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-300 text-xs hover:underline">
              Dismiss
            </button>
          </div>
        )}

        {/* Filter Toolbar */}
        <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {/* Search */}
            <div className="lg:col-span-2">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search documents by title, file name, tags..."
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Lifecycle */}
            <div>
              <select
                value={lifecycleFilter}
                onChange={(e) => setLifecycleFilter(e.target.value as DocumentLifecycleStatus | "all")}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Lifecycles</option>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="archived">Archived</option>
                <option value="expired">Expired</option>
              </select>
            </div>

            {/* Confidentiality */}
            <div>
              <select
                value={confidentialityFilter}
                onChange={(e) => setConfidentialityFilter(e.target.value as DocumentConfidentiality | "all")}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Confidentiality</option>
                <option value="public">Public</option>
                <option value="internal">Internal</option>
                <option value="confidential">Confidential</option>
                <option value="restricted">Restricted</option>
              </select>
            </div>

            {/* Sort */}
            <div>
              <select
                value={sortField}
                onChange={(e) => setSortField(e.target.value as DocumentSortField)}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="-created_at">Newest First</option>
                <option value="created_at">Oldest First</option>
                <option value="title">Title (A-Z)</option>
                <option value="-title">Title (Z-A)</option>
                <option value="-file_size">Largest Size</option>
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1 text-xs text-slate-400">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={sharedWithMe}
                onChange={(e) => setSharedWithMe(e.target.checked)}
                className="rounded border-slate-700 bg-slate-800 text-blue-600 focus:ring-blue-500"
              />
              <span>Show only documents explicitly shared with me</span>
            </label>
            {meta && (
              <span>Showing {documents.length} of {meta.total_items} items</span>
            )}
          </div>
        </div>

        {/* Documents Table */}
        <div className="rounded-2xl bg-slate-900/60 border border-slate-800 overflow-hidden shadow-xl">
          {loading ? (
            <div className="py-20 flex justify-center">
              <LoadingSpinner size="lg" />
            </div>
          ) : documents.length === 0 ? (
            <div className="p-8">
              <EmptyState
                title="No documents found"
                description="Try adjusting your search criteria, or upload your first document."
                actionLabel="Upload Document"
                onAction={() => setIsUploadModalOpen(true)}
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="bg-slate-950/60 text-xs uppercase font-semibold text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="p-4 w-10">
                      <input
                        type="checkbox"
                        checked={selectedIds.length === documents.length && documents.length > 0}
                        onChange={(e) => handleSelectAll(e.target.checked)}
                        className="rounded border-slate-700 bg-slate-800 text-blue-600"
                      />
                    </th>
                    <th className="p-4">Document</th>
                    <th className="p-4">Version</th>
                    <th className="p-4">Confidentiality</th>
                    <th className="p-4">Lifecycle</th>
                    <th className="p-4">Permission</th>
                    <th className="p-4">Created</th>
                    <th className="p-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {documents.map((doc) => {
                    const isSelected = selectedIds.includes(doc.id);
                    const canEdit = doc.user_permission === "edit" || doc.user_permission === "manage";
                    const canManage = doc.user_permission === "manage";

                    return (
                      <tr
                        key={doc.id}
                        className={`hover:bg-slate-800/40 transition ${
                          isSelected ? "bg-blue-600/10" : ""
                        }`}
                      >
                        <td className="p-4">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleSelect(doc.id)}
                            className="rounded border-slate-700 bg-slate-800 text-blue-600"
                          />
                        </td>
                        <td className="p-4">
                          <div className="space-y-1">
                            <Link
                              href={`/documents/${doc.id}`}
                              className="font-semibold text-slate-100 hover:text-blue-400 transition"
                            >
                              {doc.title || doc.file_name}
                            </Link>
                            <div className="flex items-center gap-2 text-xs text-slate-500">
                              <span>{doc.file_name}</span>
                              {doc.category && <span>• {doc.category}</span>}
                              {doc.file_size && (
                                <span>• {(doc.file_size / (1024 * 1024)).toFixed(2)} MB</span>
                              )}
                            </div>
                            {doc.tags && doc.tags.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-1">
                                {doc.tags.map((t) => (
                                  <span
                                    key={t}
                                    className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400"
                                  >
                                    #{t}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="p-4">
                          <button
                            onClick={() => setVersionDoc(doc)}
                            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono font-semibold text-blue-400 transition"
                            title="Click to view version history"
                          >
                            v{doc.current_version_number || 1}
                            {doc.version_count > 1 && (
                              <span className="text-[10px] text-slate-400 ml-1">
                                ({doc.version_count})
                              </span>
                            )}
                          </button>
                        </td>
                        <td className="p-4">{getConfidentialityBadge(doc.confidentiality)}</td>
                        <td className="p-4">{getLifecycleBadge(doc.lifecycle_status)}</td>
                        <td className="p-4">
                          <span className="capitalize text-xs font-medium px-2 py-1 rounded bg-slate-800/80 border border-slate-700 text-slate-300">
                            {doc.user_permission || "view"}
                          </span>
                        </td>
                        <td className="p-4 text-xs text-slate-400">
                          {new Date(doc.created_at).toLocaleDateString()}
                        </td>
                        <td className="p-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {/* AI Summary */}
                            <button
                              onClick={() => setSummaryDoc(doc)}
                              className="p-1.5 text-slate-400 hover:text-amber-300 hover:bg-amber-500/10 rounded-lg transition"
                              title="AI Summary"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                              </svg>
                            </button>

                            {/* AI Chat */}
                            <button
                              onClick={() => setChatDoc(doc)}
                              className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 rounded-lg transition"
                              title="AI Chat"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                              </svg>
                            </button>

                            {/* Upload New Version */}
                            {canEdit && (
                              <button
                                onClick={() => setVersionDoc(doc)}
                                className="p-1.5 text-slate-400 hover:text-purple-400 hover:bg-purple-500/10 rounded-lg transition"
                                title="Upload New Version"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                </svg>
                              </button>
                            )}

                            {/* Share */}
                            {canManage && (
                              <button
                                onClick={() => setShareDoc(doc)}
                                className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition"
                                title="Manage Access Grants"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                                </svg>
                              </button>
                            )}

                            {/* Download */}
                            <button
                              onClick={() => downloadDocument(doc.id, doc.file_name)}
                              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition"
                              title="Download File"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                              </svg>
                            </button>

                            {/* Workspace Details */}
                            <Link
                              href={`/documents/${doc.id}`}
                              className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10 rounded-lg transition"
                              title="Open Full Workspace"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>
                            </Link>

                            {/* Archive / Restore */}
                            {canManage && doc.lifecycle_status === "active" && (
                              <button
                                onClick={() => handleArchive(doc.id)}
                                className="p-1.5 text-slate-400 hover:text-amber-400 hover:bg-amber-500/10 rounded-lg transition"
                                title="Archive Document"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                                </svg>
                              </button>
                            )}
                            {canManage && doc.lifecycle_status === "archived" && (
                              <button
                                onClick={() => handleRestore(doc.id)}
                                className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition"
                                title="Restore Document"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                              </button>
                            )}

                            {/* Delete */}
                            {canManage && (
                              <button
                                onClick={() => setDeleteDoc(doc)}
                                className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition"
                                title="Delete Document"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination Footer */}
          {meta && meta.total_pages > 1 && (
            <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <div>Page {meta.page} of {meta.total_pages}</div>
              <div className="flex gap-2">
                <button
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 rounded-lg text-slate-200"
                >
                  Previous
                </button>
                <button
                  disabled={currentPage >= meta.total_pages}
                  onClick={() => setCurrentPage((p) => Math.min(p + 1, meta.total_pages))}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 rounded-lg text-slate-200"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Floating Bulk Actions Bar */}
      <BulkActionsBar
        selectedIds={selectedIds}
        onClearSelection={() => setSelectedIds([])}
        onSuccess={(result) => {
          setSuccessMessage(result.message);
          fetchDocuments();
        }}
        onError={(err) => setError(err)}
      />

      {/* Upload Document Modal */}
      <Modal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        title="Upload Document"
      >
        <form onSubmit={handleUploadSubmit} className="space-y-4">
          {uploadError && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-lg">
              {uploadError}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">File</label>
            <input
              type="file"
              required
              onChange={(e) => {
                if (e.target.files?.[0]) setUploadFile(e.target.files[0]);
              }}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Title (Optional)</label>
            <input
              type="text"
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              placeholder="e.g. Master Services Agreement 2026"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Category</label>
              <input
                type="text"
                value={uploadCategory}
                onChange={(e) => setUploadCategory(e.target.value)}
                placeholder="e.g. Legal, Finance"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Confidentiality</label>
              <select
                value={uploadConfidentiality}
                onChange={(e) => setUploadConfidentiality(e.target.value as DocumentConfidentiality)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
              >
                <option value="public">Public</option>
                <option value="internal">Internal</option>
                <option value="confidential">Confidential</option>
                <option value="restricted">Restricted</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Tags (Comma-separated)</label>
            <input
              type="text"
              value={uploadTags}
              onChange={(e) => setUploadTags(e.target.value)}
              placeholder="e.g. 2026, agreement, legal"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
            />
          </div>

          {uploading && uploadProgress !== null && (
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Uploading...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div className="bg-blue-600 h-full" style={{ width: `${uploadProgress}%` }} />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setIsUploadModalOpen(false)}
              className="px-4 py-2 bg-slate-800 text-slate-300 text-sm rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={uploading || !uploadFile}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg flex items-center gap-2"
            >
              {uploading ? <LoadingSpinner size="sm" /> : "Upload"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Feature Modals */}
      <ShareDocumentModal
        isOpen={!!shareDoc}
        onClose={() => setShareDoc(null)}
        document={shareDoc}
        onSuccess={() => {
          setSuccessMessage("Access grants updated.");
          fetchDocuments();
        }}
      />

      <UploadVersionModal
        isOpen={!!versionDoc}
        onClose={() => setVersionDoc(null)}
        document={versionDoc}
        onSuccess={() => {
          setSuccessMessage("New version uploaded.");
          fetchDocuments();
        }}
      />

      <DocumentAISummaryModal
        isOpen={!!summaryDoc}
        onClose={() => setSummaryDoc(null)}
        document={summaryDoc}
      />

      <DocumentAIChatModal
        isOpen={!!chatDoc}
        onClose={() => setChatDoc(null)}
        document={chatDoc}
      />

      {textViewerDoc && (
        <ExtractedTextViewerModal
          document={textViewerDoc}
          isOpen={!!textViewerDoc}
          onClose={() => setTextViewerDoc(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteDoc && (
        <Modal
          isOpen={!!deleteDoc}
          onClose={() => setDeleteDoc(null)}
          title="Delete Document"
        >
          <div className="space-y-4">
            <p className="text-sm text-slate-300">
              Are you sure you want to delete <strong className="text-slate-100">{deleteDoc.title || deleteDoc.file_name}</strong>?
              This will transition the document to deleted state while preserving version audit history.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteDoc(null)}
                className="px-4 py-2 bg-slate-800 text-slate-300 text-sm rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm font-semibold rounded-lg"
              >
                Delete Document
              </button>
            </div>
          </div>
        </Modal>
      )}
    </DashboardLayout>
  );
}
