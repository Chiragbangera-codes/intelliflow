"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import {
  listDocumentShares,
  shareDocument,
  revokeDocumentShare,
} from "@/services/document.service";
import apiClient from "@/services/api";
import type {
  ApiResponse,
  DocumentShare,
  DocumentSharePermission,
  EnterpriseDocument,
  User,
} from "@/types";

interface ShareDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: EnterpriseDocument | null;
  onSuccess?: () => void;
}

export function ShareDocumentModal({
  isOpen,
  onClose,
  document: doc,
  onSuccess,
}: ShareDocumentModalProps) {
  const [shares, setShares] = useState<DocumentShare[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form State
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [permission, setPermission] = useState<DocumentSharePermission>("view");
  const [expiresAt, setExpiresAt] = useState("");

  const loadShares = useCallback(async () => {
    if (!doc) return;
    try {
      setLoading(true);
      setError(null);
      const res = await listDocumentShares(doc.id);
      setShares(res.data || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load access grants.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [doc]);

  const loadUsers = useCallback(async () => {
    try {
      const res = await apiClient.get<ApiResponse<User[]>>("/employees", {
        params: { page_size: 100 },
      });
      if (res.data?.data) {
        setUsers(res.data.data);
      }
    } catch {
      // Ignore user list error gracefully
    }
  }, []);

  useEffect(() => {
    if (!isOpen || !doc) return;
    loadShares();
    loadUsers();
  }, [isOpen, doc, loadShares, loadUsers]);

  const handleShare = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!doc || !selectedUserId) return;

    try {
      setSubmitting(true);
      setError(null);
      await shareDocument(
        doc.id,
        selectedUserId,
        permission,
        expiresAt ? new Date(expiresAt).toISOString() : null,
      );
      setSuccessMsg("Access grant successfully created.");
      setSelectedUserId("");
      setExpiresAt("");
      setPermission("view");
      await loadShares();
      onSuccess?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to grant access.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (shareId: string) => {
    if (!doc) return;
    try {
      await revokeDocumentShare(doc.id, shareId);
      setSuccessMsg("Access grant revoked.");
      await loadShares();
      onSuccess?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to revoke access.";
      setError(msg);
    }
  };

  if (!doc) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Access Grants & Sharing — ${doc.title || doc.file_name}`}>
      <div className="space-y-6">
        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-lg">
            {error}
          </div>
        )}
        {successMsg && (
          <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm rounded-lg">
            {successMsg}
          </div>
        )}

        {/* Share Form */}
        <form onSubmit={handleShare} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
          <h4 className="text-sm font-semibold text-slate-200">Grant Access to User</h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Target User</label>
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                required
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select a user...</option>
                {users
                  .filter((u) => u.id !== doc.owner_id)
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.first_name} {u.last_name} ({u.email})
                    </option>
                  ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Permission Level</label>
              <select
                value={permission}
                onChange={(e) => setPermission(e.target.value as DocumentSharePermission)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="view">View (Preview & Summary)</option>
                <option value="download">Download (View + Binary File)</option>
                <option value="edit">Edit (Upload Versions / Update)</option>
                <option value="manage">Manage (Full Admin & Sharing)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Expiration (Optional)</label>
              <input
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={submitting || !selectedUserId}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium text-sm flex items-center gap-2 transition"
            >
              {submitting ? <LoadingSpinner size="sm" /> : "Grant Access"}
            </button>
          </div>
        </form>

        {/* Existing Shares List */}
        <div>
          <h4 className="text-sm font-semibold text-slate-200 mb-3">Active Access Grants</h4>
          {loading ? (
            <div className="py-6 flex justify-center">
              <LoadingSpinner size="md" />
            </div>
          ) : shares.length === 0 ? (
            <div className="text-center py-6 text-slate-500 text-sm bg-slate-900/30 rounded-lg border border-dashed border-slate-800">
              No custom access grants configured. Document is accessible only by owner, department members (if internal), and system administrators.
            </div>
          ) : (
            <div className="divide-y divide-slate-800 border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40">
              {shares.map((share) => (
                <div key={share.id} className="p-3 flex items-center justify-between hover:bg-slate-800/40 transition">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-200 text-sm">
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
                    <div className="text-xs text-slate-400 mt-0.5">
                      Granted by {share.grantor_name || "Owner"} on {new Date(share.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <button
                    onClick={() => handleRevoke(share.id)}
                    className="px-2.5 py-1 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded border border-red-500/20 transition"
                  >
                    Revoke
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
