"use client";

import React, { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { useAuthStore } from "@/store/auth.store";
import {
  getEmployees,
  getEmployeeProfile,
  createEmployeeProfile,
  updateEmployeeProfile,
} from "@/services/employee.service";
import type { EmployeeProfile, PaginationMeta } from "@/types";

export default function EmployeesPage() {
  const { user } = useAuthStore();
  const [employees, setEmployees] = useState<EmployeeProfile[]>([]);
  const [_meta, setMeta] = useState<PaginationMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Profile view / edit state
  const [selectedProfile, setSelectedProfile] = useState<EmployeeProfile | null>(null);
  const [isViewOpen, setIsViewOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    employee_code: "",
    designation: "",
    date_of_joining: "",
    salary: "",
    emergency_contact: "",
    address: "",
  });

  const canManageAll = user?.role === "admin" || user?.role === "hr";

  const refreshData = async (page: number = 1) => {
    try {
      setLoading(true);
      setError(null);
      const res = await getEmployees(page, 20);
      if (res.success) {
        setEmployees(res.data);
        if (res.meta) setMeta(res.meta);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load employee profiles";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isSubscribed = true;
    async function init() {
      try {
        const res = await getEmployees(1, 20);
        if (isSubscribed && res.success) {
          setEmployees(res.data);
          if (res.meta) setMeta(res.meta);
        }
      } catch (err: unknown) {
        if (isSubscribed) {
          const msg = err instanceof Error ? err.message : "Failed to load employee profiles";
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

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProfile) return;

    try {
      setActionLoading(true);
      setFormError(null);
      await updateEmployeeProfile(selectedProfile.user_id, {
        employee_code: formData.employee_code || undefined,
        designation: formData.designation || undefined,
        date_of_joining: formData.date_of_joining || undefined,
        salary: formData.salary ? Number(formData.salary) : undefined,
        emergency_contact: formData.emergency_contact || undefined,
        address: formData.address || undefined,
      });
      setIsEditOpen(false);
      refreshData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update profile";
      setFormError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateOwnSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;

    try {
      setActionLoading(true);
      setFormError(null);
      await createEmployeeProfile(user.id, {
        employee_code: formData.employee_code || undefined,
        designation: formData.designation || undefined,
        date_of_joining: formData.date_of_joining || undefined,
        salary: formData.salary ? Number(formData.salary) : undefined,
        emergency_contact: formData.emergency_contact || undefined,
        address: formData.address || undefined,
      });
      setIsCreateOpen(false);
      refreshData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create profile";
      setFormError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const openViewModal = async (profile: EmployeeProfile) => {
    try {
      const res = await getEmployeeProfile(profile.user_id);
      setSelectedProfile(res.data);
      setIsViewOpen(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to fetch profile details";
      alert(msg);
    }
  };

  const openEditModal = (profile: EmployeeProfile) => {
    setSelectedProfile(profile);
    setFormData({
      employee_code: profile.employee_code || "",
      designation: profile.designation || "",
      date_of_joining: profile.date_of_joining || "",
      salary: profile.salary ? String(profile.salary) : "",
      emergency_contact: profile.emergency_contact || "",
      address: profile.address || "",
    });
    setFormError(null);
    setIsEditOpen(true);
  };

  return (
    <DashboardLayout>
      <div style={{ maxWidth: 1200 }}>
        {/* Page Header */}
        <div style={{ marginBottom: 40 }}>
          <p className="eyebrow" style={{ color: "var(--accent)", marginBottom: 12 }}>
            People & Directory
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
              Employees &
              <br />
              <span style={{ color: "var(--ink-40)" }}>team member records.</span>
            </h1>

            {user && !employees.some((e) => e.user_id === user.id) && (
              <button
                onClick={() => {
                  setFormData({
                    employee_code: "",
                    designation: "",
                    date_of_joining: "",
                    salary: "",
                    emergency_contact: "",
                    address: "",
                  });
                  setFormError(null);
                  setIsCreateOpen(true);
                }}
                className="btn btn-primary"
                style={{ flexShrink: 0 }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Setup My Profile
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <LoadingSpinner size="lg" message="Loading employee directory..." />
        ) : error ? (
          <div style={{ padding: "12px 16px", background: "rgb(220 38 38 / 0.08)", border: "1px solid rgb(220 38 38 / 0.2)", borderRadius: 8, fontSize: 13, color: "#f87171" }}>
            {error}
          </div>
        ) : employees.length === 0 ? (
          <EmptyState
            title="No profiles found"
            description="No active employee profiles are registered in your access scope."
            actionLabel={user ? "Setup My Profile" : undefined}
            onAction={user ? () => setIsCreateOpen(true) : undefined}
          />
        ) : (
          <div style={{ background: "var(--ink-90)", border: "1px solid var(--ink-70)", borderRadius: 12, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="table-enterprise">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Code</th>
                    <th>Designation</th>
                    <th>Role</th>
                    <th>Start Date</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.map((emp) => {
                    const canEditThis = canManageAll || user?.id === emp.user_id;
                    return (
                      <tr key={emp.id}>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <div
                              style={{
                                width: 28,
                                height: 28,
                                borderRadius: 6,
                                background: "var(--ink-80)",
                                border: "1px solid var(--ink-70)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                fontSize: 11,
                                fontWeight: 700,
                                color: "#93c5fd",
                              }}
                            >
                              {emp.first_name?.[0]}
                              {emp.last_name?.[0]}
                            </div>
                            <div>
                              <p style={{ fontWeight: 600, color: "#f1f5f9", margin: 0, fontSize: 13 }}>
                                {emp.first_name} {emp.last_name}
                              </p>
                              <p style={{ fontSize: 11, color: "var(--ink-40)", margin: 0 }}>
                                {emp.email}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td style={{ fontFamily: "monospace", fontSize: 12 }}>
                          {emp.employee_code || "—"}
                        </td>
                        <td style={{ color: "#cbd5e1" }}>
                          {emp.designation || "—"}
                        </td>
                        <td>
                          <Badge variant="primary" size="sm">
                            {emp.role}
                          </Badge>
                        </td>
                        <td style={{ fontSize: 12 }}>
                          {emp.date_of_joining ? String(emp.date_of_joining) : "—"}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
                            <button
                              onClick={() => openViewModal(emp)}
                              className="btn btn-ghost btn-sm"
                            >
                              View
                            </button>
                            {canEditThis && (
                              <button
                                onClick={() => openEditModal(emp)}
                                className="btn btn-ghost btn-sm"
                              >
                                Edit
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
          </div>
        )}

        {/* View Profile Modal */}
        <Modal
          isOpen={isViewOpen}
          onClose={() => setIsViewOpen(false)}
          title="Employee Profile Details"
          maxWidth="lg"
        >
          {selectedProfile && (
            <div className="space-y-6">
              <div className="flex items-center gap-4 pb-4 border-b border-gray-100 dark:border-gray-800">
                <div className="w-14 h-14 rounded-2xl bg-blue-600 text-white font-bold text-lg flex items-center justify-center shadow-md shadow-blue-600/20">
                  {selectedProfile.first_name?.[0]}
                  {selectedProfile.last_name?.[0]}
                </div>
                <div>
                  <h4 className="text-lg font-bold text-gray-900 dark:text-white">
                    {selectedProfile.first_name} {selectedProfile.last_name}
                  </h4>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{selectedProfile.email}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-xs font-medium text-gray-400 block">Designation</span>
                  <span className="font-semibold text-gray-900 dark:text-white">
                    {selectedProfile.designation || "Not assigned"}
                  </span>
                </div>

                <div>
                  <span className="text-xs font-medium text-gray-400 block">Employee Code</span>
                  <span className="font-semibold text-gray-900 dark:text-white font-mono">
                    {selectedProfile.employee_code || "Not assigned"}
                  </span>
                </div>

                <div>
                  <span className="text-xs font-medium text-gray-400 block">Date of Joining</span>
                  <span className="font-semibold text-gray-900 dark:text-white">
                    {selectedProfile.date_of_joining ? String(selectedProfile.date_of_joining) : "—"}
                  </span>
                </div>

                <div>
                  <span className="text-xs font-medium text-gray-400 block">System Role</span>
                  <Badge variant="primary" size="sm" className="mt-1">
                    {selectedProfile.role}
                  </Badge>
                </div>

                <div>
                  <span className="text-xs font-medium text-gray-400 block">Emergency Contact</span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {selectedProfile.emergency_contact || "—"}
                  </span>
                </div>

                <div>
                  <span className="text-xs font-medium text-gray-400 block">Address</span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {selectedProfile.address || "—"}
                  </span>
                </div>
              </div>

              <div className="flex justify-end pt-4 border-t border-gray-100 dark:border-gray-800">
                <button
                  type="button"
                  onClick={() => setIsViewOpen(false)}
                  className="px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-sm font-medium rounded-xl hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          )}
        </Modal>

        {/* Edit / Setup Profile Modal */}
        <Modal
          isOpen={isEditOpen || isCreateOpen}
          onClose={() => {
            setIsEditOpen(false);
            setIsCreateOpen(false);
          }}
          title={isCreateOpen ? "Create Employee Profile" : "Edit Employee Profile"}
        >
          <form
            onSubmit={isCreateOpen ? handleCreateOwnSubmit : handleEditSubmit}
            className="space-y-4"
          >
            {formError && (
              <div className="p-3 text-xs bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 rounded-xl border border-rose-200 dark:border-rose-800">
                {formError}
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Employee Code
                </label>
                <input
                  type="text"
                  value={formData.employee_code}
                  onChange={(e) => setFormData({ ...formData, employee_code: e.target.value })}
                  placeholder="e.g. EMP-0042"
                  className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Designation
                </label>
                <input
                  type="text"
                  value={formData.designation}
                  onChange={(e) => setFormData({ ...formData, designation: e.target.value })}
                  placeholder="e.g. Senior Engineer"
                  className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Date of Joining
                </label>
                <input
                  type="date"
                  value={formData.date_of_joining}
                  onChange={(e) => setFormData({ ...formData, date_of_joining: e.target.value })}
                  className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {canManageAll && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Salary (Gross)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.salary}
                    onChange={(e) => setFormData({ ...formData, salary: e.target.value })}
                    placeholder="90000.00"
                    className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Emergency Contact
              </label>
              <input
                type="text"
                value={formData.emergency_contact}
                onChange={(e) => setFormData({ ...formData, emergency_contact: e.target.value })}
                placeholder="Name and phone number"
                className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Address
              </label>
              <textarea
                rows={2}
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                placeholder="Mailing address"
                className="w-full px-3.5 py-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setIsEditOpen(false);
                  setIsCreateOpen(false);
                }}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {actionLoading ? "Saving..." : isCreateOpen ? "Create Profile" : "Save Changes"}
              </button>
            </div>
          </form>
        </Modal>
      </div>
    </DashboardLayout>
  );
}
