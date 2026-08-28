/**
 * Dashboard stats service.
 *
 * Provides API client calls for dashboard statistics.
 */

import apiClient from "./api";
import type { ApiResponse, DashboardStats } from "@/types";

export async function getDashboardStats(): Promise<ApiResponse<DashboardStats>> {
  const response = await apiClient.get<ApiResponse<DashboardStats>>("/dashboard/stats");
  return response.data;
}
