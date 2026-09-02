/**
 * Admin Security and System Observability API Client Service.
 */

import apiClient from "@/services/api";
import type {
  ActiveSession,
  SecurityEventListResponse,
  SecuritySummaryResponse,
  SystemMetricsResponse,
} from "@/types/security";

export interface SecurityEventFilterParams {
  action?: string;
  user_id?: string;
  severity?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
}

export const securityService = {
  /**
   * Fetch paginated and filtered security events (Admin only).
   */
  async listSecurityEvents(
    params: SecurityEventFilterParams = {},
  ): Promise<SecurityEventListResponse> {
    const res = await apiClient.get<SecurityEventListResponse>(
      "/admin/security/events",
      { params },
    );
    return res.data;
  },

  /**
   * Fetch 24-hour aggregate security metrics (Admin only).
   */
  async getSecuritySummary(): Promise<SecuritySummaryResponse> {
    const res = await apiClient.get<SecuritySummaryResponse>(
      "/admin/security/summary",
    );
    return res.data;
  },

  /**
   * Fetch system-wide telemetry and health metrics (Admin only).
   */
  async getSystemMetrics(): Promise<SystemMetricsResponse> {
    const res = await apiClient.get<SystemMetricsResponse>(
      "/admin/system/metrics",
    );
    return res.data;
  },

  /**
   * Revoke all active sessions for current user across all devices.
   */
  async revokeAllSessions(): Promise<{ success: boolean; message: string; data: { revoked_count: number } }> {
    const res = await apiClient.post("/auth/revoke-all");
    return res.data;
  },

  /**
   * List active sessions for the current user.
   */
  async listActiveSessions(): Promise<{ success: boolean; data: ActiveSession[] }> {
    const res = await apiClient.get("/auth/sessions");
    return res.data;
  },

  /**
   * Probe system readiness.
   */
  async getHealthReadiness(): Promise<Record<string, unknown>> {
    const res = await apiClient.get("/health/ready");
    return res.data;
  },
};

export default securityService;
