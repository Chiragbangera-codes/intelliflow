export type IntegrationProvider = 'webhook' | 'slack' | 'msteams' | 'email' | 'generic_http';

export type IntegrationStatus = 'active' | 'inactive' | 'error';

export interface Integration {
  id: string;
  provider: IntegrationProvider;
  name: string;
  description: string | null;
  status: IntegrationStatus;
  configuration: Record<string, unknown>;
  has_credentials: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  last_synced_at: string | null;
}

export interface IntegrationCreatePayload {
  provider: IntegrationProvider;
  name: string;
  description?: string | null;
  configuration: Record<string, unknown>;
  credentials?: Record<string, unknown> | null;
  status?: IntegrationStatus;
}

export interface IntegrationUpdatePayload {
  name?: string | null;
  description?: string | null;
  configuration?: Record<string, unknown> | null;
  credentials?: Record<string, unknown> | null;
  status?: IntegrationStatus | null;
}

export interface IntegrationListResponse {
  items: Integration[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface IntegrationTestResult {
  success: boolean;
  status_code?: number | null;
  response?: string | null;
  error?: string | null;
  message?: string | null;
}
