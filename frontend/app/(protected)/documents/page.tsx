"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
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

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatFileSize(bytes?: number | null): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffH = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffH < 1) return "Just now";
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function getFileTypeLabel(filename: string): string {
  const ext = filename.split(".").pop()?.toUpperCase() || "DOC";
  return ext;
}

// ─── Document Row Component ──────────────────────────────────────────────────

interface DocRowProps {
  doc: EnterpriseDocument;
  isSelected: boolean;
  onToggle: () => void;
  onSummary: () => void;
  onChat: () => void;
  onVersion: () => void;
  onShare: () => void;
  onDownload: () => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
}

const DocRow: React.FC<DocRowProps> = ({
  doc,
  isSelected,
  onToggle,
  onSummary,
  onChat,
  onVersion,
  onShare,
  onDownload,
  onArchive,
  onRestore,
  onDelete,
}) => {
  const [hovered, setHovered] = React.useState(false);
  const canEdit = doc.user_permission === "edit" || doc.user_permission === "manage";
  const canManage = doc.user_permission === "manage";
  const fileType = getFileTypeLabel(doc.file_name);

  const lifecycleClass =
    doc.lifecycle_status === "active" ? "badge-active"
    : doc.lifecycle_status === "draft" ? "badge-draft"
    : doc.lifecycle_status === "archived" ? "badge-archived"
    : doc.lifecycle_status === "expired" ? "badge-expired"
    : "badge-deleted";

  const confClass =
    doc.confidentiality === "public" ? "badge-public"
    : doc.confidentiality === "internal" ? "badge-internal"
    : doc.confidentiality === "confidential" ? "badge-confidential"
    : "badge-restricted";

  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: isSelected
          ? "rgb(31 92 246 / 0.06)"
          : hovered
          ? "rgb(255 255 255 / 0.02)"
          : "transparent",
        transition: "background 0.1s",
      }}
    >
      {/* Checkbox */}
      <td style={{ padding: "14px 16px", width: 40 }}>
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggle}
          style={{
            width: 14,
            height: 14,
            accentColor: "var(--accent)",
            cursor: "pointer",
          }}
        />
      </td>

      {/* Document — primary column */}
      <td style={{ padding: "14px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Document artifact thumbnail */}
          <div
            style={{
              width: 36,
              height: 46,
              background: "var(--ink-80)",
              border: "1px solid var(--ink-70)",
              borderRadius: 6,
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              padding: "6px 5px",
              flexShrink: 0,
              position: "relative",
              overflow: "hidden",
            }}
          >
            {/* Folded corner */}
            <div
              style={{
                position: "absolute",
                top: 0,
                right: 0,
                width: 9,
                height: 9,
                background: "var(--ink-90)",
                borderBottomLeftRadius: 3,
                borderLeft: "1px solid var(--ink-70)",
                borderBottom: "1px solid var(--ink-70)",
              }}
            />
            {/* Content lines */}
            <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 3 }}>
              <div style={{ height: 2, background: "var(--ink-60)", borderRadius: 1, width: "60%" }} />
              <div style={{ height: 2, background: "var(--ink-70)", borderRadius: 1, width: "85%" }} />
              <div style={{ height: 2, background: "var(--ink-70)", borderRadius: 1, width: "70%" }} />
            </div>
            {/* Extension tag */}
            <span
              style={{
                fontSize: 8,
                fontWeight: 800,
                color: "#93c5fd",
                letterSpacing: "0.04em",
                lineHeight: 1,
                fontFamily: "monospace",
                textTransform: "uppercase",
              }}
            >
              {fileType.slice(0, 4)}
            </span>
          </div>

          {/* Title + meta */}
          <div style={{ minWidth: 0 }}>
            <Link
              href={`/documents/${doc.id}`}
              style={{
                display: "block",
                fontSize: 14,
                fontWeight: 600,
                color: "#e2e8f0",
                textDecoration: "none",
                letterSpacing: "-0.01em",
                lineHeight: 1.3,
                marginBottom: 3,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: 260,
                transition: "color 0.1s",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = "#93c5fd"; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = "#e2e8f0"; }}
            >
              {doc.title || doc.file_name}
            </Link>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "var(--ink-40)" }}>{doc.file_name}</span>
              {doc.category && (
                <span style={{ fontSize: 11, color: "var(--ink-60)" }}>· {doc.category}</span>
              )}
              {doc.file_size && (
                <span style={{ fontSize: 11, color: "var(--ink-60)" }}>· {formatFileSize(doc.file_size)}</span>
              )}
            </div>
            {doc.tags && doc.tags.length > 0 && (
              <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                {doc.tags.slice(0, 3).map((t) => (
                  <span
                    key={t}
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      background: "var(--ink-80)",
                      border: "1px solid var(--ink-70)",
                      borderRadius: 3,
                      color: "var(--ink-40)",
                    }}
                  >
                    #{t}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </td>

      {/* Version */}
      <td style={{ padding: "14px 16px" }}>
        <button
          onClick={onVersion}
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: "var(--ink-40)",
            background: "var(--ink-80)",
            border: "1px solid var(--ink-70)",
            borderRadius: 4,
            padding: "3px 8px",
            cursor: "pointer",
            fontFamily: "monospace",
            letterSpacing: "0.02em",
            transition: "all 0.1s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--accent)";
            e.currentTarget.style.color = "#93c5fd";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--ink-70)";
            e.currentTarget.style.color = "var(--ink-40)";
          }}
          title="View version history"
        >
          v{doc.current_version_number || 1}
          {doc.version_count > 1 && (
            <span style={{ fontSize: 9, color: "var(--ink-60)", marginLeft: 3 }}>
              /{doc.version_count}
            </span>
          )}
        </button>
      </td>

      {/* Confidentiality */}
      <td style={{ padding: "14px 16px" }}>
        <span className={`badge ${confClass}`}>{doc.confidentiality}</span>
      </td>

      {/* Status */}
      <td style={{ padding: "14px 16px" }}>
        <span className={`badge ${lifecycleClass}`}>{doc.lifecycle_status}</span>
      </td>

      {/* Permission */}
      <td style={{ padding: "14px 16px" }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "var(--ink-40)",
            textTransform: "capitalize",
            letterSpacing: "0.02em",
          }}
        >
          {doc.user_permission || "view"}
        </span>
      </td>

      {/* Date */}
      <td style={{ padding: "14px 16px" }}>
        <span style={{ fontSize: 12, color: "var(--ink-40)" }}>
          {formatDate(doc.created_at)}
        </span>
      </td>

      {/* Actions */}
      <td style={{ padding: "14px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 2 }}>
          <ActionBtn title="AI Summary" onClick={onSummary} color="#fbbf24">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </ActionBtn>
          <ActionBtn title="AI Chat" onClick={onChat} color="#93c5fd">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            </svg>
          </ActionBtn>
          {canEdit && (
            <ActionBtn title="Upload Version" onClick={onVersion} color="#c4b5fd">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
              </svg>
            </ActionBtn>
          )}
          {canManage && (
            <ActionBtn title="Manage Access" onClick={onShare} color="#4ade80">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
            </ActionBtn>
          )}
          <ActionBtn title="Download" onClick={onDownload} color="#94a3b8">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
            </svg>
          </ActionBtn>
          <Link
            href={`/documents/${doc.id}`}
            title="Open Document"
            style={{
              width: 26,
              height: 26,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 5,
              color: "var(--ink-60)",
              transition: "all 0.1s",
              border: "1px solid transparent",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgb(31 92 246 / 0.1)";
              e.currentTarget.style.color = "#93c5fd";
              e.currentTarget.style.borderColor = "rgb(31 92 246 / 0.2)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--ink-60)";
              e.currentTarget.style.borderColor = "transparent";
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </Link>
          {canManage && doc.lifecycle_status === "active" && (
            <ActionBtn title="Archive" onClick={onArchive} color="#fbbf24">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="21 8 21 21 3 21 3 8" /><rect x="1" y="3" width="22" height="5" /><line x1="10" y1="12" x2="14" y2="12" />
              </svg>
            </ActionBtn>
          )}
          {canManage && doc.lifecycle_status === "archived" && (
            <ActionBtn title="Restore" onClick={onRestore} color="#4ade80">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8" /><path d="M3 3v5h5" />
              </svg>
            </ActionBtn>
          )}
          {canManage && (
            <ActionBtn title="Delete" onClick={onDelete} color="#f87171">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14H6L5 6M10 11v6M14 11v6M9 6V4h6v2" />
              </svg>
            </ActionBtn>
          )}
        </div>
      </td>
    </tr>
  );
};

// Small icon button helper
const ActionBtn: React.FC<{
  title: string;
  onClick: () => void;
  color: string;
  children: React.ReactNode;
}> = ({ title, onClick, color, children }) => (
  <button
    onClick={onClick}
    title={title}
    style={{
      width: 26,
      height: 26,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: 5,
      border: "1px solid transparent",
      background: "transparent",
      color: "var(--ink-60)",
      cursor: "pointer",
      transition: "all 0.1s",
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.color = color;
      e.currentTarget.style.background = `${color}14`;
      e.currentTarget.style.borderColor = `${color}30`;
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.color = "var(--ink-60)";
      e.currentTarget.style.background = "transparent";
      e.currentTarget.style.borderColor = "transparent";
    }}
  >
    {children}
  </button>
);

// ─── Main Page ───────────────────────────────────────────────────────────────

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

  // Multi-Selection
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Modals
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadCategory, setUploadCategory] = useState("General");
  const [uploadConfidentiality, setUploadConfidentiality] = useState<DocumentConfidentiality>("internal");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [shareDoc, setShareDoc] = useState<EnterpriseDocument | null>(null);
  const [versionDoc, setVersionDoc] = useState<EnterpriseDocument | null>(null);
  const [summaryDoc, setSummaryDoc] = useState<EnterpriseDocument | null>(null);
  const [chatDoc, setChatDoc] = useState<EnterpriseDocument | null>(null);
  const [textViewerDoc, setTextViewerDoc] = useState<EnterpriseDocument | null>(null);
  const [deleteDoc, setDeleteDoc] = useState<EnterpriseDocument | null>(null);

  // Debounce
  useEffect(() => {
    const timer = setTimeout(() => { setDebouncedSearch(search); setCurrentPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [search]);

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
        setError(err instanceof Error ? err.message : "Failed to load documents.");
      } finally {
        setLoading(false);
      }
    },
    [currentPage, debouncedSearch, lifecycleFilter, confidentialityFilter, sharedWithMe, sortField],
  );

  useEffect(() => { fetchDocuments(currentPage); }, [fetchDocuments, currentPage]);

  const handleSelectAll = (checked: boolean) => {
    setSelectedIds(checked ? documents.map((d) => d.id) : []);
  };

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;
    try {
      setUploading(true);
      setUploadError(null);
      const parsedTags = uploadTags.split(",").map((t) => t.trim()).filter(Boolean);
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
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const handleArchive = async (id: string) => {
    try { await archiveDocument(id); setSuccessMessage("Document archived."); fetchDocuments(); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "Archive failed."); }
  };

  const handleRestore = async (id: string) => {
    try { await restoreDocument(id); setSuccessMessage("Document restored."); fetchDocuments(); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "Restore failed."); }
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

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1300 }}>

        {/* ── Page header ── */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            marginBottom: 40,
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div>
            <p className="eyebrow" style={{ color: "var(--accent)", marginBottom: 12 }}>
              Document Library
            </p>
            <h1
              style={{
                fontFamily: "var(--font-jakarta, var(--font-inter, sans-serif))",
                fontSize: "clamp(1.75rem, 3vw, 2.5rem)",
                fontWeight: 800,
                letterSpacing: "-0.04em",
                color: "#f8fafc",
                lineHeight: 1.1,
                margin: 0,
              }}
            >
              Your organization&apos;s knowledge,
              <br />
              <span style={{ color: "var(--ink-40)" }}>organized and ready to move.</span>
            </h1>
          </div>
          <button
            onClick={() => setIsUploadModalOpen(true)}
            className="btn btn-primary"
            style={{ flexShrink: 0 }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Upload Document
          </button>
        </div>

        {/* ── Status banners ── */}
        {successMessage && (
          <div
            style={{
              marginBottom: 16,
              padding: "11px 16px",
              background: "rgb(22 163 74 / 0.08)",
              border: "1px solid rgb(22 163 74 / 0.2)",
              borderRadius: 8,
              fontSize: 13,
              color: "#4ade80",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>{successMessage}</span>
            <button
              onClick={() => setSuccessMessage(null)}
              style={{ background: "none", border: "none", color: "#4ade80", fontSize: 12, cursor: "pointer", opacity: 0.7 }}
            >
              Dismiss
            </button>
          </div>
        )}
        {error && (
          <div
            style={{
              marginBottom: 16,
              padding: "11px 16px",
              background: "rgb(220 38 38 / 0.08)",
              border: "1px solid rgb(220 38 38 / 0.2)",
              borderRadius: 8,
              fontSize: 13,
              color: "#f87171",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              style={{ background: "none", border: "none", color: "#f87171", fontSize: 12, cursor: "pointer", opacity: 0.7 }}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* ── Filter toolbar ── */}
        <div
          style={{
            display: "flex",
            gap: 10,
            marginBottom: 24,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          {/* Search */}
          <div style={{ position: "relative", flex: "1 1 240px", minWidth: 200 }}>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--ink-60)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
            >
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search documents..."
              className="input"
              style={{ paddingLeft: 36 }}
            />
          </div>

          <select
            value={lifecycleFilter}
            onChange={(e) => setLifecycleFilter(e.target.value as DocumentLifecycleStatus | "all")}
            className="input"
            style={{ flex: "0 1 160px" }}
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="draft">Draft</option>
            <option value="archived">Archived</option>
            <option value="expired">Expired</option>
          </select>

          <select
            value={confidentialityFilter}
            onChange={(e) => setConfidentialityFilter(e.target.value as DocumentConfidentiality | "all")}
            className="input"
            style={{ flex: "0 1 180px" }}
          >
            <option value="all">All Access Levels</option>
            <option value="public">Public</option>
            <option value="internal">Internal</option>
            <option value="confidential">Confidential</option>
            <option value="restricted">Restricted</option>
          </select>

          <select
            value={sortField}
            onChange={(e) => setSortField(e.target.value as DocumentSortField)}
            className="input"
            style={{ flex: "0 1 160px" }}
          >
            <option value="-created_at">Newest First</option>
            <option value="created_at">Oldest First</option>
            <option value="title">Title A–Z</option>
            <option value="-title">Title Z–A</option>
            <option value="-file_size">Largest</option>
          </select>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 13,
              color: "var(--ink-40)",
              cursor: "pointer",
              userSelect: "none",
              whiteSpace: "nowrap",
              paddingLeft: 4,
            }}
          >
            <input
              type="checkbox"
              checked={sharedWithMe}
              onChange={(e) => setSharedWithMe(e.target.checked)}
              style={{ accentColor: "var(--accent)", width: 13, height: 13 }}
            />
            Shared with me
          </label>

          {meta && (
            <span style={{ fontSize: 12, color: "var(--ink-60)", marginLeft: "auto", whiteSpace: "nowrap" }}>
              {documents.length} / {meta.total_items}
            </span>
          )}
        </div>

        {/* ── Document Table ── */}
        <div
          style={{
            background: "var(--ink-90)",
            border: "1px solid var(--ink-70)",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          {loading ? (
            <LoadingSpinner size="lg" message="Loading documents..." />
          ) : documents.length === 0 ? (
            <EmptyState
              title="No documents found"
              description="Try adjusting your search or filters, or upload your first document to begin building your knowledge library."
              actionLabel="Upload Document"
              onAction={() => setIsUploadModalOpen(true)}
            />
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="table-enterprise" style={{ minWidth: 900 }}>
                <thead>
                  <tr>
                    <th style={{ width: 40, paddingLeft: 16 }}>
                      <input
                        type="checkbox"
                        checked={selectedIds.length === documents.length && documents.length > 0}
                        onChange={(e) => handleSelectAll(e.target.checked)}
                        style={{ width: 13, height: 13, accentColor: "var(--accent)" }}
                      />
                    </th>
                    <th>Document</th>
                    <th>Version</th>
                    <th>Access</th>
                    <th>Status</th>
                    <th>Permission</th>
                    <th>Updated</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <DocRow
                      key={doc.id}
                      doc={doc}
                      isSelected={selectedIds.includes(doc.id)}
                      onToggle={() => handleToggleSelect(doc.id)}
                      onSummary={() => setSummaryDoc(doc)}
                      onChat={() => setChatDoc(doc)}
                      onVersion={() => setVersionDoc(doc)}
                      onShare={() => setShareDoc(doc)}
                      onDownload={() => downloadDocument(doc.id, doc.file_name)}
                      onArchive={() => handleArchive(doc.id)}
                      onRestore={() => handleRestore(doc.id)}
                      onDelete={() => setDeleteDoc(doc)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {meta && meta.total_pages > 1 && (
            <div
              style={{
                padding: "14px 20px",
                borderTop: "1px solid var(--ink-70)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span style={{ fontSize: 12, color: "var(--ink-40)" }}>
                Page {meta.page} of {meta.total_pages}
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                  className="btn btn-ghost btn-sm"
                  style={{ opacity: currentPage <= 1 ? 0.4 : 1 }}
                >
                  ← Previous
                </button>
                <button
                  disabled={currentPage >= meta.total_pages}
                  onClick={() => setCurrentPage((p) => Math.min(p + 1, meta.total_pages))}
                  className="btn btn-ghost btn-sm"
                  style={{ opacity: currentPage >= meta.total_pages ? 0.4 : 1 }}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Bulk Actions Bar ── */}
      <BulkActionsBar
        selectedIds={selectedIds}
        onClearSelection={() => setSelectedIds([])}
        onSuccess={(result) => { setSuccessMessage(result.message); fetchDocuments(); }}
        onError={(err) => setError(err)}
      />

      {/* ── Upload Modal ── */}
      <Modal isOpen={isUploadModalOpen} onClose={() => setIsUploadModalOpen(false)} title="Upload Document">
        <form onSubmit={handleUploadSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {uploadError && (
            <div style={{ padding: "10px 14px", background: "rgb(220 38 38 / 0.08)", border: "1px solid rgb(220 38 38 / 0.2)", borderRadius: 8, fontSize: 13, color: "#f87171" }}>
              {uploadError}
            </div>
          )}

          <div>
            <label className="input-label">File *</label>
            <input
              type="file"
              required
              onChange={(e) => { if (e.target.files?.[0]) setUploadFile(e.target.files[0]); }}
              className="input"
              style={{ padding: "8px 12px", cursor: "pointer" }}
            />
          </div>

          <div>
            <label className="input-label">Title (Optional)</label>
            <input
              type="text"
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              placeholder="e.g. Master Services Agreement 2026"
              className="input"
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="input-label">Category</label>
              <input
                type="text"
                value={uploadCategory}
                onChange={(e) => setUploadCategory(e.target.value)}
                placeholder="e.g. Legal, Finance"
                className="input"
              />
            </div>
            <div>
              <label className="input-label">Access Level</label>
              <select
                value={uploadConfidentiality}
                onChange={(e) => setUploadConfidentiality(e.target.value as DocumentConfidentiality)}
                className="input"
              >
                <option value="public">Public</option>
                <option value="internal">Internal</option>
                <option value="confidential">Confidential</option>
                <option value="restricted">Restricted</option>
              </select>
            </div>
          </div>

          <div>
            <label className="input-label">Tags (comma-separated)</label>
            <input
              type="text"
              value={uploadTags}
              onChange={(e) => setUploadTags(e.target.value)}
              placeholder="e.g. 2026, agreement, legal"
              className="input"
            />
          </div>

          {uploading && uploadProgress !== null && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12, color: "var(--ink-40)" }}>
                <span>Uploading...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div style={{ height: 3, background: "var(--ink-70)", borderRadius: 2, overflow: "hidden" }}>
                <div
                  style={{
                    height: "100%",
                    width: `${uploadProgress}%`,
                    background: "var(--accent)",
                    borderRadius: 2,
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, paddingTop: 4 }}>
            <button
              type="button"
              onClick={() => setIsUploadModalOpen(false)}
              className="btn btn-ghost"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={uploading || !uploadFile}
              className="btn btn-primary"
            >
              {uploading ? (
                <>
                  <span style={{ width: 12, height: 12, border: "2px solid rgb(255 255 255 / 0.3)", borderTopColor: "white", borderRadius: "50%", animation: "spin 0.7s linear infinite", display: "inline-block" }} />
                  Uploading...
                </>
              ) : (
                "Upload Document"
              )}
            </button>
          </div>
        </form>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </Modal>

      {/* Feature Modals — unchanged logic */}
      <ShareDocumentModal
        isOpen={!!shareDoc}
        onClose={() => setShareDoc(null)}
        document={shareDoc}
        onSuccess={() => { setSuccessMessage("Access grants updated."); fetchDocuments(); }}
      />
      <UploadVersionModal
        isOpen={!!versionDoc}
        onClose={() => setVersionDoc(null)}
        document={versionDoc}
        onSuccess={() => { setSuccessMessage("New version uploaded."); fetchDocuments(); }}
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

      {/* Delete Confirmation */}
      {deleteDoc && (
        <Modal
          isOpen={!!deleteDoc}
          onClose={() => setDeleteDoc(null)}
          title="Delete Document"
          size="sm"
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <p style={{ fontSize: 14, color: "#94a3b8", lineHeight: 1.6 }}>
              Delete <strong style={{ color: "#f1f5f9" }}>{deleteDoc.title || deleteDoc.file_name}</strong>?
              <br />
              The document will be marked as deleted while preserving the version audit history.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button onClick={() => setDeleteDoc(null)} className="btn btn-ghost">Cancel</button>
              <button onClick={handleDeleteConfirm} className="btn btn-danger">Delete Document</button>
            </div>
          </div>
        </Modal>
      )}
    </DashboardLayout>
  );
}
