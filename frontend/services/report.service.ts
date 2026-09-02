/**
 * Reports API service — Phase 9.
 */

import apiClient from "./api";
import type { ApiResponse, PaginationMeta } from "@/types";
import type { Report, ReportGenerateRequest } from "@/types/analytics";

const BASE = "/reports";

export async function requestReport(
  data: ReportGenerateRequest,
): Promise<ApiResponse<Report>> {
  const res = await apiClient.post<ApiResponse<Report>>(BASE, data);
  return res.data;
}

export async function listReports(params?: {
  page?: number;
  page_size?: number;
}): Promise<{ success: boolean; message: string; data: Report[]; meta: PaginationMeta }> {
  const res = await apiClient.get(BASE, { params });
  return res.data;
}

export async function getReport(id: string): Promise<ApiResponse<Report>> {
  const res = await apiClient.get<ApiResponse<Report>>(`${BASE}/${id}`);
  return res.data;
}
