"use client";

import React, { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { useAuthStore } from "@/store/auth.store";
import {
  getDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment,
} from "@/services/department.service";
import type { Department, PaginationMeta } from "@/types";

export default function DepartmentsPage() {
  const { user } = useAuthStore();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [_meta, setMeta] = useState<PaginationMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [selectedDept, setSelectedDept] = useState<Department | null>(null);
  const [formData, setFormData] = useState({ name: "", description: "" });
  const [actionLoading, setActionLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const canManage = user?.role === "admin" || user?.role === "hr";

  const refreshData = async (page: number = 1) => {
    try {
      setLoading(true);
      setError(null);
      const res = await getDepartments(page, 20);
      if (res.success) {
        setDepartments(res.data);
        if (res.meta) setMeta(res.meta);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load departments";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isSubscribed = true;
    async function init() {
      try {
        const res = await getDepartments(1, 20);
        if (isSubscribed && res.success) {
          setDepartments(res.data);
          if (res.meta) setMeta(res.meta);
        }
      } catch (err: unknown) {
        if (isSubscribed) {
          const msg = err instanceof Error ? err.message : "Failed to load departments";
          setError(msg);
        }
      } finally {
        if (isSubscribed) {
          setLoading(false);
        }
      }
    }
    init();
    return () => {
      isSubscribed = false;
    };
  }, []);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) return;

    try {
      setActionLoading(true);
      setFormError(null);
      await createDepartment({
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
      });
      setIsCreateOpen(false);
      setFormData({ name: "", description: "" });
      refreshData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create department";
      setFormError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDept || !formData.name.trim()) return;

    try {
      setActionLoading(true);
      setFormError(null);
      await updateDepartment(selectedDept.id, {
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
      });
      setIsEditOpen(false);
      setSelectedDept(null);
      setFormData({ name: "", description: "" });
      refreshData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update department";
      setFormError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (dept: Department) => {
    if (!confirm(`Are you sure you want to delete "${dept.name}"?`)) return;

    try {
      await deleteDepartment(dept.id);
      refreshData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete department";
      alert(msg);
    }
  };

  const openEditModal = (dept: Department) => {
    setSelectedDept(dept);
    setFormData({ name: dept.name, description: dept.description || "" });
    setFormError(null);
    setIsEditOpen(true);
  };

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1200 }}>
        {/* Page Header */}
        <div style={{ marginBottom: 40 }}>
          <p className="eyebrow" style={{ color: "var(--accent)", marginBottom: 12 }}>
            Organization
          </p>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
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
              Departments &
              <br />
              <span style={{ color: "var(--ink-40)" }}>organizational divisions.</span>
            </h1>

            {canManage && (
              <button
                onClick={() => {
                  setFormData({ name: "", description: "" });
                  setFormError(null);
                  setIsCreateOpen(true);
                }}
                className="btn btn-primary"
                style={{ flexShrink: 0 }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                New Department
              </button>
            )}
          </div>
        </div>

        {/* Content table */}
        {loading ? (
          <LoadingSpinner size="lg" message="Loading departments..." />
        ) : error ? (
          <div style={{ padding: "12px 16px", background: "rgb(220 38 38 / 0.08)", border: "1px solid rgb(220 38 38 / 0.2)", borderRadius: 8, fontSize: 13, color: "#f87171" }}>
            {error}
          </div>
        ) : departments.length === 0 ? (
          <EmptyState
            title="No departments yet"
            description="Get started by creating your first organizational department."
            actionLabel={canManage ? "Create Department" : undefined}
            onAction={canManage ? () => setIsCreateOpen(true) : undefined}
          />
        ) : (
          <div style={{ background: "var(--ink-90)", border: "1px solid var(--ink-70)", borderRadius: 12, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="table-enterprise">
                <thead>
                  <tr>
                    <th>Department Name</th>
                    <th>Description</th>
                    <th>Created</th>
                    {canManage && <th style={{ textAlign: "right" }}>Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {departments.map((dept) => (
                    <tr key={dept.id}>
                      <td style={{ fontWeight: 600, color: "#f1f5f9" }}>{dept.name}</td>
                      <td>{dept.description || "—"}</td>
                      <td style={{ fontSize: 12 }}>{new Date(dept.created_at).toLocaleDateString()}</td>
                      {canManage && (
                        <td style={{ textAlign: "right" }}>
                          <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
                            <button
                              onClick={() => openEditModal(dept)}
                              className="btn btn-ghost btn-sm"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDelete(dept)}
                              className="btn btn-sm"
                              style={{ background: "transparent", border: "1px solid transparent", color: "#f87171", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Create Modal */}
        <Modal
          isOpen={isCreateOpen}
          onClose={() => setIsCreateOpen(false)}
          title="Create New Department"
        >
          <form onSubmit={handleCreateSubmit} className="space-y-4">
            {formError && (
              <div className="p-3 text-xs bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 rounded-xl border border-rose-200 dark:border-rose-800">
                {formError}
              </div>
            )}
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Department Name *
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g. Finance, Product, Operations"
                className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Description
              </label>
              <textarea
                rows={3}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Brief summary of department responsibilities..."
                className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {actionLoading ? "Creating..." : "Create Department"}
              </button>
            </div>
          </form>
        </Modal>

        {/* Edit Modal */}
        <Modal
          isOpen={isEditOpen}
          onClose={() => setIsEditOpen(false)}
          title="Edit Department"
        >
          <form onSubmit={handleEditSubmit} className="space-y-4">
            {formError && (
              <div className="p-3 text-xs bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 rounded-xl border border-rose-200 dark:border-rose-800">
                {formError}
              </div>
            )}
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Department Name *
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Description
              </label>
              <textarea
                rows={3}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsEditOpen(false)}
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
      </div>
    </DashboardLayout>
  );
}
