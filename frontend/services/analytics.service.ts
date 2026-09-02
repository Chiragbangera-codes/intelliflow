/**
 * Analytics API service — Phase 9.
 *
 * Wraps all GET /api/v1/analytics/* endpoints.
 */

import apiClient from "./api";
import type { ApiResponse } from "@/types";
import type {
  AIUsageAnalytics,
  DepartmentAnalytics,
  DocumentAnalytics,
  EmployeeAnalytics,
  KPISummary,
  RevenueAnalytics,
  WorkflowAnalytics,
} from "@/types/analytics";

const BASE = "/analytics";

export async function getKPISummary(): Promise<ApiResponse<KPISummary>> {
  const res = await apiClient.get<ApiResponse<KPISummary>>(`${BASE}/kpi`);
  return res.data;
}

export async function getRevenueAnalytics(
  year?: number,
): Promise<ApiResponse<RevenueAnalytics>> {
  const params = year ? { year } : {};
  const res = await apiClient.get<ApiResponse<RevenueAnalytics>>(
    `${BASE}/revenue`,
    { params },
  );
  return res.data;
}

export async function getDepartmentAnalytics(): Promise<
  ApiResponse<DepartmentAnalytics>
> {
  const res = await apiClient.get<ApiResponse<DepartmentAnalytics>>(
    `${BASE}/departments`,
  );
  return res.data;
}

export async function getEmployeeAnalytics(): Promise<
  ApiResponse<EmployeeAnalytics>
> {
  const res = await apiClient.get<ApiResponse<EmployeeAnalytics>>(
    `${BASE}/employees`,
  );
  return res.data;
}

export async function getDocumentAnalytics(): Promise<
  ApiResponse<DocumentAnalytics>
> {
  const res = await apiClient.get<ApiResponse<DocumentAnalytics>>(
    `${BASE}/documents`,
  );
  return res.data;
}

export async function getWorkflowAnalytics(): Promise<
  ApiResponse<WorkflowAnalytics>
> {
  const res = await apiClient.get<ApiResponse<WorkflowAnalytics>>(
    `${BASE}/workflows`,
  );
  return res.data;
}

export async function getAIUsageAnalytics(): Promise<
  ApiResponse<AIUsageAnalytics>
> {
  const res = await apiClient.get<ApiResponse<AIUsageAnalytics>>(`${BASE}/ai`);
  return res.data;
}
