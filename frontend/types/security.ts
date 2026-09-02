/**
 * TypeScript types for Security Events, Health, and System Observability.
 */

export type SecuritySeverity = "info" | "warning" | "critical";

export interface SecurityEvent {
  id: string;
  action: string;
  severity: SecuritySeverity;
  user_id: string | null;
  user_email: string | null;
  ip_address: string | null;
  user_agent: string | null;
  status: "success" | "failure";
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface SecurityEventPagination {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface SecurityEventListResponse {
  success: boolean;
  data: SecurityEvent[];
  pagination: SecurityEventPagination;
}

export interface SecuritySummaryData {
  total_events: number;
  failed_logins_24h: number;
  rate_limit_exceeded_24h: number;
  unauthorized_attempts_24h: number;
  critical_events_24h: number;
  token_reuse_detected_24h: number;
  active_sessions_count: number;
}

export interface SecuritySummaryResponse {
  success: boolean;
  data: SecuritySummaryData;
}

export interface ActiveSession {
  id: string;
  user_id: string;
  created_at: string;
  expires_at: string;
  is_current?: boolean;
}

export interface DependencyHealth {
  status: "healthy" | "degraded" | "unhealthy";
  latency_ms?: number;
  details?: Record<string, unknown>;
}

export interface SystemMetrics {
  status: string;
  uptime_seconds: number;
  memory_usage_mb: number;
  environment: string;
  database_status: string;
  database_latency_ms: number | null;
  redis_status: string;
  redis_latency_ms: number | null;
  celery_status: string;
  ai_status: string;
  faiss_vectors: number;
  total_users_count: number;
  total_documents_count: number;
  total_workflows_count: number;
  total_executions_count: number;
  timestamp: string;
}

export interface SystemMetricsResponse {
  success: boolean;
  data: SystemMetrics;
}
