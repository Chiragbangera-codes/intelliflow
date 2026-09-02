/**
 * Milestone 11 — Document Intelligence & Management TypeScript Types.
 */

export type DocumentStatus = "pending" | "processing" | "processed" | "failed";
export type OcrStatus = "pending" | "processing" | "completed" | "failed" | "skipped";

export type DocumentLifecycleStatus =
  | "draft"
  | "active"
  | "archived"
  | "expired"
  | "deleted";

export type DocumentConfidentiality =
  | "public"
  | "internal"
  | "confidential"
  | "restricted";

export type DocumentSharePermission =
  | "view"
  | "download"
  | "edit"
  | "manage";

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  file_name: string;
  storage_path: string;
  file_type?: string | null;
  file_size?: number | null;
  checksum?: string | null;
  created_by: string;
  creator_name?: string | null;
  is_current: boolean;
  change_summary?: string | null;
  created_at: string;
}

export interface DocumentShare {
  id: string;
  document_id: string;
  user_id: string;
  user_email?: string | null;
  user_name?: string | null;
  granted_by: string;
  grantor_name?: string | null;
  permission: DocumentSharePermission;
  expires_at?: string | null;
  created_at: string;
  revoked_at?: string | null;
  is_active: boolean;
}

export interface EnterpriseDocument {
  id: string;
  file_name: string;
  title: string;
  description?: string | null;
  category?: string | null;
  document_type?: string | null;
  tags: string[];
  storage_path: string;
  file_type?: string | null;
  file_size?: number | null;
  owner_id: string;
  department_id?: string | null;
  confidentiality: DocumentConfidentiality;
  lifecycle_status: DocumentLifecycleStatus;
  status: DocumentStatus;
  ocr_status: OcrStatus;
  checksum?: string | null;
  retention_period_days?: number | null;
  activated_at?: string | null;
  archived_at?: string | null;
  expires_at?: string | null;
  created_at: string;
  updated_at: string;
  version_count: number;
  current_version_number: number;
  user_permission?: DocumentSharePermission | null;
}

export interface DocumentChunkSource {
  chunk_id: string;
  document_id: string;
  document_name: string;
  chunk_number: number;
  content: string;
  distance?: number;
  similarity?: number;
  file_type?: string | null;
  created_at?: string;
}

export interface DocumentAISummaryResponse {
  document_id: string;
  document_name: string;
  summary: string;
  chunks_used: number;
  sources: DocumentChunkSource[];
}

export interface DocumentAIChatRequest {
  message: string;
  conversation_id?: string;
  top_k?: number;
  min_score?: number;
}

export interface DocumentAIChatResponse {
  document_id: string;
  document_name: string;
  answer: string;
  conversation_id: string;
  sources: DocumentChunkSource[];
}

export interface DocumentActivityItem {
  id: string;
  action: string;
  actor_id?: string | null;
  actor_name: string;
  actor_email?: string | null;
  timestamp: string;
  summary: string;
  details: Record<string, unknown>;
}

export interface DocumentActivityResponse {
  document_id: string;
  data: DocumentActivityItem[];
  total_events: number;
}

export interface BulkOperationResultItem {
  document_id: string;
  success: boolean;
  reason?: string | null;
}

export interface BulkOperationResponse {
  message: string;
  total: number;
  succeeded: number;
  failed: number;
  results: BulkOperationResultItem[];
}

export interface DocumentQueryParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: DocumentStatus | "all";
  lifecycle_status?: DocumentLifecycleStatus | "all";
  department_id?: string;
  owner_id?: string;
  category?: string;
  document_type?: string;
  confidentiality?: DocumentConfidentiality | "all";
  tag?: string;
  shared_with_me?: boolean;
  date_from?: string;
  date_to?: string;
  sort?: string;
}
