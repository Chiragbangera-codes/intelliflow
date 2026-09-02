"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { ShareDocumentModal } from "@/components/documents/ShareDocumentModal";
import { UploadVersionModal } from "@/components/documents/UploadVersionModal";
import {
  getDocument,
  downloadDocument,
  previewDocumentBlob,
  listDocumentVersions,
  restoreDocumentVersion,
  downloadDocumentVersion,
  listDocumentShares,
  revokeDocumentShare,
  getDocumentAISummary,
  askDocumentAIChat,
  getDocumentActivity,
  archiveDocument,
  restoreDocument,
  deleteDocument,
  updateDocument,
} from "@/services/document.service";
import { getDocumentText } from "@/services/ocr.service";
import type {
  DocumentAISummaryResponse,
  DocumentActivityItem,
  DocumentChunk,
  DocumentChunkSource,
  DocumentConfidentiality,
  DocumentShare,
  DocumentVersion,
  EnterpriseDocument,
} from "@/types";

type ActiveTab =
  | "overview"
  | "preview"
  | "versions"
  | "ai"
  | "shares"
  | "activity";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: DocumentChunkSource[];
  timestamp: Date;
}

export default function DocumentDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const documentId = params?.id as string;

  const [doc, setDoc] = useState<EnterpriseDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("overview");

  // Feature Data States
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);

  const [shares, setShares] = useState<DocumentShare[]>([]);
  const [sharesLoading, setSharesLoading] = useState(false);

  const [activity, setActivity] = useState<DocumentActivityItem[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);

  const [summaryData, setSummaryData] = useState<DocumentAISummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const [extractedChunks, setExtractedChunks] = useState<DocumentChunk[]>([]);

  // Chat State
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // Preview Blob State
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewContentType, setPreviewContentType] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);

  // Modals
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);
  const [isVersionModalOpen, setIsVersionModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editConfidentiality, setEditConfidentiality] = useState<DocumentConfidentiality>("internal");
  const [editTags, setEditTags] = useState("");

  // Load Main Document
  const loadDoc = useCallback(async () => {
    if (!documentId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await getDocument(documentId);
      setDoc(res.data);
      setEditTitle(res.data.title || res.data.file_name);
      setEditCategory(res.data.category || "General");
      setEditConfidentiality(res.data.confidentiality);
      setEditTags((res.data.tags || []).join(", "));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load document.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    loadDoc();
  }, [loadDoc]);

  // Tab Data Loaders
  useEffect(() => {
    if (!documentId) return;

    if (activeTab === "versions") {
      (async () => {
        try {
          setVersionsLoading(true);
          const res = await listDocumentVersions(documentId);
          setVersions(res.data || []);
        } catch {
          // ignore
        } finally {
          setVersionsLoading(false);
        }
      })();
    } else if (activeTab === "shares") {
      (async () => {
        try {
          setSharesLoading(true);
          const res = await listDocumentShares(documentId);
          setShares(res.data || []);
        } catch {
          // ignore
        } finally {
          setSharesLoading(false);
        }
      })();
    } else if (activeTab === "activity") {
      (async () => {
        try {
          setActivityLoading(true);
          const res = await getDocumentActivity(documentId);
          setActivity(res.data.data || []);
        } catch {
          // ignore
        } finally {
          setActivityLoading(false);
        }
      })();
    } else if (activeTab === "ai") {
      if (!summaryData) {
        (async () => {
          try {
            setSummaryLoading(true);
            const res = await getDocumentAISummary(documentId);
            setSummaryData(res.data);
          } catch {
            // ignore
          } finally {
            setSummaryLoading(false);
          }
        })();
      }
    } else if (activeTab === "preview") {
      (async () => {
        try {
          setPreviewLoading(true);
          const { blobUrl, contentType } = await previewDocumentBlob(documentId);
          setPreviewBlobUrl(blobUrl);
          setPreviewContentType(contentType);

          // Load extracted text chunks
          const textRes = await getDocumentText(documentId);
          if (textRes.data?.chunks) {
            setExtractedChunks(textRes.data.chunks);
          }
        } catch {
          // ignore
        } finally {
          setPreviewLoading(false);
        }
      })();
    }
  }, [activeTab, documentId, summaryData]);

  // Scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // Version restore
  const handleRestoreVersion = async (versionId: string) => {
    if (!confirm("Restore this historical version as the current document revision?")) return;
    try {
      await restoreDocumentVersion(documentId, versionId);
      setSuccessMsg("Historical version restored as new revision.");
      await loadDoc();
      const res = await listDocumentVersions(documentId);
      setVersions(res.data || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to restore version.");
    }
  };

  // AI Chat query
  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const q = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [
      ...prev,
      { role: "user", content: q, timestamp: new Date() },
    ]);

    try {
      setChatLoading(true);
      const res = await askDocumentAIChat(documentId, {
        message: q,
        conversation_id: conversationId,
      });
      setConversationId(res.data.conversation_id);
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.data.answer,
          sources: res.data.sources,
          timestamp: new Date(),
        },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "AI query failed.";
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${msg}`, timestamp: new Date() },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // Lifecycle actions
  const handleArchive = async () => {
    try {
      await archiveDocument(documentId);
      setSuccessMsg("Document archived.");
      await loadDoc();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Archive failed.");
    }
  };

  const handleRestoreLifecycle = async () => {
    try {
      await restoreDocument(documentId);
      setSuccessMsg("Document restored to active state.");
      await loadDoc();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Restore failed.");
    }
  };

  const handleDelete = async () => {
    if (!confirm("Are you sure you want to delete this document?")) return;
    try {
      await deleteDocument(documentId);
      router.push("/documents");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const tags = editTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await updateDocument(documentId, {
        title: editTitle,
        category: editCategory,
        confidentiality: editConfidentiality,
        tags,
      });
      setSuccessMsg("Document metadata updated.");
      setIsEditModalOpen(false);
      await loadDoc();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update metadata.");
    }
  };

  if (loading && !doc) {
    return (
      <DashboardLayout>
        <div className="py-24 flex justify-center">
          <LoadingSpinner size="lg" />
        </div>
      </DashboardLayout>
    );
  }

  if (!doc) {
    return (
      <DashboardLayout>
        <div className="p-8 text-center space-y-4">
          <div className="text-red-400 font-semibold">Document Not Found</div>
          <Link href="/documents" className="text-blue-400 text-sm hover:underline">
            Back to Documents
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  const canEdit = doc.user_permission === "edit" || doc.user_permission === "manage";
  const canManage = doc.user_permission === "manage";

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Breadcrumb & Navigation */}
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Link href="/documents" className="hover:text-slate-200 transition">
            Documents
          </Link>
          <span>/</span>
          <span className="text-slate-200 font-medium truncate max-w-md">
            {doc.title || doc.file_name}
          </span>
        </div>

        {/* Top Header Card */}
        <div className="p-6 rounded-2xl bg-slate-900/70 border border-slate-800 shadow-xl space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="text-2xl font-bold text-slate-100 tracking-tight">
                  {doc.title || doc.file_name}
                </h1>
                <Badge variant="primary" className="font-mono text-xs">
                  v{doc.current_version_number || 1}
                </Badge>
                <Badge variant="neutral" className="uppercase text-xs">
                  {doc.confidentiality}
                </Badge>
                <Badge
                  variant={doc.lifecycle_status === "active" ? "success" : "warning"}
                  className="capitalize text-xs"
                >
                  {doc.lifecycle_status}
                </Badge>
                <span className="capitalize text-xs font-medium px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300">
                  {doc.user_permission || "view"} Access
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                <span>File: <strong className="text-slate-300">{doc.file_name}</strong></span>
                {doc.file_size && (
                  <span>• Size: <strong className="text-slate-300">{(doc.file_size / (1024 * 1024)).toFixed(2)} MB</strong></span>
                )}
                {doc.category && (
                  <span>• Category: <strong className="text-slate-300">{doc.category}</strong></span>
                )}
                <span>• Created: {new Date(doc.created_at).toLocaleDateString()}</span>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => downloadDocument(doc.id, doc.file_name)}
                className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-2 transition"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download
              </button>

              {canEdit && (
                <button
                  onClick={() => setIsVersionModalOpen(true)}
                  className="px-3.5 py-2 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 text-xs font-semibold flex items-center gap-2 transition"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  New Version
                </button>
              )}

              {canManage && (
                <button
                  onClick={() => setIsShareModalOpen(true)}
                  className="px-3.5 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-semibold flex items-center gap-2 transition"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                  </svg>
                  Access Grants
                </button>
              )}

              {canManage && (
                <button
                  onClick={() => setIsEditModalOpen(true)}
                  className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition"
                >
                  Edit Metadata
                </button>
              )}
            </div>
          </div>

          {/* Banners */}
          {successMsg && (
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs rounded-xl flex items-center justify-between">
              <span>{successMsg}</span>
              <button onClick={() => setSuccessMsg(null)} className="text-emerald-300 hover:underline">
                Dismiss
              </button>
            </div>
          )}
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded-xl flex items-center justify-between">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="text-red-300 hover:underline">
                Dismiss
              </button>
            </div>
          )}
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 gap-2 overflow-x-auto">
          {[
            { id: "overview", label: "Overview & Properties" },
            { id: "preview", label: "Preview & Extracted Text" },
            { id: "versions", label: `Version History (${doc.version_count || 1})` },
            { id: "ai", label: "Document AI Intelligence" },
            { id: "shares", label: "Access Grants & Sharing" },
            { id: "activity", label: "Activity Audit Timeline" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as ActiveTab)}
              className={`px-4 py-3 text-sm font-semibold border-b-2 whitespace-nowrap transition ${
                activeTab === tab.id
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab 1: Overview & Properties */}
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
              <h3 className="text-base font-semibold text-slate-100">Document Properties</h3>
              <div className="divide-y divide-slate-800 text-sm">
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">Title</span>
                  <span className="text-slate-200 font-medium">{doc.title || "—"}</span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">File Name</span>
                  <span className="text-slate-200 font-mono text-xs">{doc.file_name}</span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">MIME / File Type</span>
                  <span className="text-slate-200">{doc.file_type || "application/octet-stream"}</span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">SHA-256 Checksum</span>
                  <span className="text-slate-200 font-mono text-xs truncate max-w-[200px]" title={doc.checksum || ""}>
                    {doc.checksum || "—"}
                  </span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">Current Revision</span>
                  <span className="text-blue-400 font-semibold">Version {doc.current_version_number || 1}</span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">Total Versions</span>
                  <span className="text-slate-200">{doc.version_count || 1}</span>
                </div>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
              <h3 className="text-base font-semibold text-slate-100">Enterprise & Compliance</h3>
              <div className="divide-y divide-slate-800 text-sm">
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">Confidentiality</span>
                  <span className="capitalize font-medium text-slate-200">{doc.confidentiality}</span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">Lifecycle Status</span>
                  <span className="capitalize font-medium text-slate-200">{doc.lifecycle_status}</span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">OCR & Search Status</span>
                  <Badge variant={doc.ocr_status === "completed" ? "success" : "warning"} className="text-xs capitalize">
                    {doc.ocr_status}
                  </Badge>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">Retention Period</span>
                  <span className="text-slate-200">
                    {doc.retention_period_days ? `${doc.retention_period_days} days` : "Indefinite"}
                  </span>
                </div>
                <div className="py-2.5 flex justify-between">
                  <span className="text-slate-400">Expiration Date</span>
                  <span className="text-slate-200">
                    {doc.expires_at ? new Date(doc.expires_at).toLocaleDateString() : "No expiration set"}
                  </span>
                </div>
              </div>

              {/* Tags */}
              <div className="pt-2">
                <span className="text-xs text-slate-400 block mb-2 font-medium">Categorization Tags</span>
                {doc.tags && doc.tags.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {doc.tags.map((t) => (
                      <span key={t} className="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300">
                        #{t}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500">No tags assigned.</div>
                )}
              </div>

              {/* Lifecycle Controls */}
              {canManage && (
                <div className="pt-4 border-t border-slate-800 flex gap-2">
                  {doc.lifecycle_status === "active" ? (
                    <button
                      onClick={handleArchive}
                      className="px-3 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-semibold transition"
                    >
                      Archive Document
                    </button>
                  ) : (
                    <button
                      onClick={handleRestoreLifecycle}
                      className="px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-semibold transition"
                    >
                      Activate Document
                    </button>
                  )}

                  <button
                    onClick={handleDelete}
                    className="px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 text-xs font-semibold transition"
                  >
                    Delete Document
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Preview & Extracted Text */}
        {activeTab === "preview" && (
          <div className="space-y-6">
            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-slate-100">In-Browser File Preview</h3>
                <button
                  onClick={() => downloadDocument(doc.id, doc.file_name)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg font-medium"
                >
                  Download Original
                </button>
              </div>

              {previewLoading ? (
                <div className="py-20 flex justify-center">
                  <LoadingSpinner size="lg" />
                </div>
              ) : previewBlobUrl ? (
                <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950 h-[600px] flex items-center justify-center">
                  {previewContentType.includes("pdf") ? (
                    <iframe src={previewBlobUrl} className="w-full h-full" title="PDF Preview" />
                  ) : previewContentType.includes("image") ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={previewBlobUrl} alt="Preview" className="max-h-full object-contain" />
                  ) : (
                    <div className="text-center p-6 space-y-2">
                      <p className="text-sm text-slate-400">
                        Binary preview not natively supported for {previewContentType}.
                      </p>
                      <button
                        onClick={() => downloadDocument(doc.id, doc.file_name)}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-semibold"
                      >
                        Download File to View
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-12 text-center text-slate-500 text-sm">Preview unavailable.</div>
              )}
            </div>

            {/* Extracted Text Chunks */}
            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
              <h3 className="text-base font-semibold text-slate-100">
                Extracted Text Chunks ({extractedChunks.length})
              </h3>
              {extractedChunks.length === 0 ? (
                <div className="text-xs text-slate-500">No extracted text chunks found for this document.</div>
              ) : (
                <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
                  {extractedChunks.map((chunk) => (
                    <div
                      key={chunk.id}
                      className="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-xs space-y-1.5"
                    >
                      <span className="font-semibold text-blue-400">Chunk #{chunk.chunk_number}</span>
                      <p className="text-slate-300 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
                        {chunk.content}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 3: Version History */}
        {activeTab === "versions" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-100">Document Revisions</h3>
                <p className="text-xs text-slate-400">
                  Non-destructive revision tree. Any past version can be downloaded or restored as the current revision.
                </p>
              </div>
              {canEdit && (
                <button
                  onClick={() => setIsVersionModalOpen(true)}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-xl transition"
                >
                  Upload New Revision
                </button>
              )}
            </div>

            {versionsLoading ? (
              <div className="py-16 flex justify-center">
                <LoadingSpinner size="md" />
              </div>
            ) : versions.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-sm">No versions found.</div>
            ) : (
              <div className="divide-y divide-slate-800 border border-slate-800 rounded-2xl overflow-hidden bg-slate-900/60 shadow-xl">
                {versions.map((ver) => (
                  <div key={ver.id} className="p-4 flex items-center justify-between hover:bg-slate-800/40 transition">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-100 text-sm">
                          Version {ver.version_number}
                        </span>
                        {ver.is_current && (
                          <Badge variant="success" className="text-xs">
                            Current Revision
                          </Badge>
                        )}
                        <span className="font-mono text-xs text-slate-400">{ver.file_name}</span>
                      </div>
                      <p className="text-xs text-slate-300 italic">
                        &ldquo;{ver.change_summary || "No notes provided"}&rdquo;
                      </p>
                      <div className="flex items-center gap-3 text-[11px] text-slate-500">
                        <span>Created on {new Date(ver.created_at).toLocaleDateString()}</span>
                        {ver.file_size && (
                          <span>• {(ver.file_size / (1024 * 1024)).toFixed(2)} MB</span>
                        )}
                        {ver.checksum && (
                          <span className="font-mono" title={ver.checksum}>
                            • Checksum: {ver.checksum.slice(0, 12)}...
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => downloadDocumentVersion(doc.id, ver.id, ver.file_name)}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg font-medium transition"
                      >
                        Download
                      </button>
                      {canEdit && !ver.is_current && (
                        <button
                          onClick={() => handleRestoreVersion(ver.id)}
                          className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/30 text-xs rounded-lg font-medium transition"
                        >
                          Restore as Current
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 4: Document AI Intelligence */}
        {activeTab === "ai" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Executive Summary */}
            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                  <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Executive AI Summary
                </h3>
                <button
                  onClick={async () => {
                    setSummaryLoading(true);
                    try {
                      const res = await getDocumentAISummary(documentId);
                      setSummaryData(res.data);
                    } finally {
                      setSummaryLoading(false);
                    }
                  }}
                  disabled={summaryLoading}
                  className="px-3 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg"
                >
                  Regenerate
                </button>
              </div>

              {summaryLoading ? (
                <div className="py-16 flex flex-col items-center justify-center space-y-3">
                  <LoadingSpinner size="md" />
                  <p className="text-xs text-slate-400">Synthesizing document summary...</p>
                </div>
              ) : summaryData ? (
                <div className="space-y-4">
                  <div className="text-xs text-slate-400">
                    Grounded synthesis across {summaryData.chunks_used} document text chunks.
                  </div>
                  <div className="prose prose-invert text-xs text-slate-200 bg-slate-950/60 p-4 rounded-xl border border-slate-800 whitespace-pre-wrap leading-relaxed">
                    {summaryData.summary}
                  </div>
                </div>
              ) : (
                <div className="py-8 text-center text-slate-500 text-xs">Summary not available.</div>
              )}
            </div>

            {/* Document-Scoped AI Chat */}
            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 flex flex-col h-[580px]">
              <h3 className="text-base font-semibold text-slate-100 mb-2 flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                Document-Scoped Q&A
              </h3>
              <p className="text-xs text-slate-400 mb-3">
                Queries are strictly grounded in this document with prompt injection defenses.
              </p>

              {/* Chat Messages */}
              <div className="flex-1 overflow-y-auto space-y-3 p-2 border border-slate-800/80 rounded-xl bg-slate-950/40">
                {chatMessages.length === 0 && (
                  <div className="text-center py-12 text-slate-500 text-xs">
                    Ask any question about this document to get started.
                  </div>
                )}
                {chatMessages.map((m, idx) => (
                  <div
                    key={idx}
                    className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
                  >
                    <div
                      className={`max-w-[88%] rounded-xl px-3.5 py-2.5 text-xs leading-relaxed ${
                        m.role === "user"
                          ? "bg-blue-600 text-white rounded-br-none"
                          : "bg-slate-800 text-slate-100 border border-slate-700 rounded-bl-none"
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{m.content}</div>
                      {m.sources && m.sources.length > 0 && (
                        <div className="mt-2 pt-1.5 border-t border-slate-700/60 text-[10px] space-y-1">
                          <span className="font-semibold text-slate-400">Cited Chunks:</span>
                          {m.sources.slice(0, 2).map((s) => (
                            <div key={s.chunk_id} className="text-slate-400 italic">
                              • Chunk #{s.chunk_number}: &ldquo;{s.content.slice(0, 100)}...&rdquo;
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="flex items-center gap-2 text-slate-400 text-xs p-1">
                    <LoadingSpinner size="sm" />
                    <span>Searching chunks & generating grounded answer...</span>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Chat Form */}
              <form onSubmit={handleSendChat} className="mt-3 flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Ask a question..."
                  disabled={chatLoading}
                  className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="submit"
                  disabled={chatLoading || !chatInput.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold rounded-xl"
                >
                  Ask
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Tab 5: Access Grants & Sharing */}
        {activeTab === "shares" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-100">Access Grants</h3>
                <p className="text-xs text-slate-400">
                  Explicit user-level access permissions with optional expiration windows.
                </p>
              </div>
              {canManage && (
                <button
                  onClick={() => setIsShareModalOpen(true)}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-xl transition"
                >
                  Grant User Access
                </button>
              )}
            </div>

            {sharesLoading ? (
              <div className="py-16 flex justify-center">
                <LoadingSpinner size="md" />
              </div>
            ) : shares.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm border border-dashed border-slate-800 rounded-xl">
                No custom access grants. Only the owner, department members (if internal), and administrators can access this document.
              </div>
            ) : (
              <div className="divide-y divide-slate-800 border border-slate-800 rounded-2xl overflow-hidden bg-slate-900/60 shadow-xl">
                {shares.map((share) => (
                  <div key={share.id} className="p-4 flex items-center justify-between hover:bg-slate-800/40 transition">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100 text-sm">
                          {share.user_name || share.user_email || "User"}
                        </span>
                        <Badge variant="primary" className="capitalize text-xs">
                          {share.permission}
                        </Badge>
                        {share.expires_at && (
                          <span className="text-xs text-amber-400">
                            Expires: {new Date(share.expires_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        Granted by {share.grantor_name || "Owner"} on {new Date(share.created_at).toLocaleDateString()}
                      </div>
                    </div>

                    {canManage && (
                      <button
                        onClick={async () => {
                          await revokeDocumentShare(doc.id, share.id);
                          setSuccessMsg("Access grant revoked.");
                          const res = await listDocumentShares(doc.id);
                          setShares(res.data || []);
                        }}
                        className="px-3 py-1.5 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg border border-red-500/20 transition"
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 6: Activity Audit Timeline */}
        {activeTab === "activity" && (
          <div className="space-y-4">
            <h3 className="text-base font-semibold text-slate-100">Document Activity Timeline</h3>
            {activityLoading ? (
              <div className="py-16 flex justify-center">
                <LoadingSpinner size="md" />
              </div>
            ) : activity.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">No activity recorded.</div>
            ) : (
              <div className="space-y-3">
                {activity.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-start justify-between gap-4 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="font-semibold text-slate-200">{item.summary}</div>
                      <div className="text-slate-500">
                        Action: <code className="text-slate-400">{item.action}</code>
                      </div>
                    </div>
                    <div className="text-slate-400 whitespace-nowrap">
                      {new Date(item.timestamp).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Share Modal */}
      <ShareDocumentModal
        isOpen={isShareModalOpen}
        onClose={() => setIsShareModalOpen(false)}
        document={doc}
        onSuccess={async () => {
          const res = await listDocumentShares(doc.id);
          setShares(res.data || []);
        }}
      />

      {/* Version Modal */}
      <UploadVersionModal
        isOpen={isVersionModalOpen}
        onClose={() => setIsVersionModalOpen(false)}
        document={doc}
        onSuccess={async () => {
          await loadDoc();
          const res = await listDocumentVersions(doc.id);
          setVersions(res.data || []);
        }}
      />

      {/* Edit Metadata Modal */}
      {isEditModalOpen && (
        <Modal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          title="Edit Document Metadata"
        >
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Title</label>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                required
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Category</label>
                <input
                  type="text"
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Confidentiality</label>
                <select
                  value={editConfidentiality}
                  onChange={(e) => setEditConfidentiality(e.target.value as DocumentConfidentiality)}
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
                value={editTags}
                onChange={(e) => setEditTags(e.target.value)}
                placeholder="e.g. 2026, agreement"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsEditModalOpen(false)}
                className="px-4 py-2 bg-slate-800 text-slate-300 text-sm rounded-lg"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg"
              >
                Save Changes
              </button>
            </div>
          </form>
        </Modal>
      )}
    </DashboardLayout>
  );
}
