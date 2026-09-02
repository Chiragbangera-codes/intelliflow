/**
 * TypeScript type definitions and interfaces.
 *
 * Shared types used across features.
 */

// ---------------------------------------------------------------------------
// API Response envelopes
// ---------------------------------------------------------------------------

/** Pagination metadata included in list responses. */
export interface PaginationMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

/** Standard API success response wrapper. */
export interface ApiResponse<T = unknown> {
  success: boolean;
  message: string;
  data: T;
  meta?: PaginationMeta;
}

/** Standard API error response. */
export interface ApiErrorResponse {
  success: false;
  message: string;
  detail?: string | { field: string; message: string }[];
}

// ---------------------------------------------------------------------------
// User & Auth types
// ---------------------------------------------------------------------------

/** User roles defined in the system. */
export type UserRole = "admin" | "manager" | "employee" | "hr" | "finance";

/** User account status. */
export type UserStatus = "active" | "inactive" | "suspended";

/** Safe user profile — no password hash ever included. */
export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  status: UserStatus;
  last_login?: string | null;
}

/** Authentication tokens returned after login/refresh. */
export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface LogoutRequest {
  refresh_token: string;
}

// ---------------------------------------------------------------------------
// Department types
// ---------------------------------------------------------------------------

export interface Department {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateDepartmentRequest {
  name: string;
  description?: string | null;
}

export interface UpdateDepartmentRequest {
  name?: string | null;
  description?: string | null;
}

// ---------------------------------------------------------------------------
// Employee Profile types
// ---------------------------------------------------------------------------

export interface EmployeeProfile {
  id: string;
  user_id: string;
  employee_code?: string | null;
  date_of_joining?: string | null;
  designation?: string | null;
  salary?: string | number | null;
  manager_id?: string | null;
  emergency_contact?: string | null;
  address?: string | null;
  profile_photo?: string | null;
  created_at: string;
  updated_at: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
}

export interface CreateEmployeeProfileRequest {
  employee_code?: string | null;
  date_of_joining?: string | null;
  designation?: string | null;
  salary?: number | null;
  manager_id?: string | null;
  emergency_contact?: string | null;
  address?: string | null;
  profile_photo?: string | null;
}

export interface UpdateEmployeeProfileRequest {
  employee_code?: string | null;
  date_of_joining?: string | null;
  designation?: string | null;
  salary?: number | null;
  manager_id?: string | null;
  emergency_contact?: string | null;
  address?: string | null;
  profile_photo?: string | null;
}

// ---------------------------------------------------------------------------
// Document types (Milestone 11)
// ---------------------------------------------------------------------------

import type {
  DocumentConfidentiality,
  EnterpriseDocument,
} from "./document";

export * from "./document";

export type Document = EnterpriseDocument;

export interface CreateDocumentRequest {
  file_name: string;
  storage_path: string;
  file_type?: string | null;
  file_size?: number | null;
  checksum?: string | null;
  title?: string;
  description?: string | null;
  category?: string | null;
  document_type?: string | null;
  tags?: string[];
  department_id?: string | null;
  confidentiality?: DocumentConfidentiality;
  retention_period_days?: number | null;
  expires_at?: string | null;
}

export interface UpdateDocumentRequest {
  title?: string;
  description?: string | null;
  category?: string | null;
  document_type?: string | null;
  tags?: string[];
  department_id?: string | null;
  confidentiality?: DocumentConfidentiality;
  retention_period_days?: number | null;
  expires_at?: string | null;
  file_name?: string | null;
  file_type?: string | null;
  checksum?: string | null;
}

export type DocumentSortField =
  | "created_at"
  | "-created_at"
  | "updated_at"
  | "-updated_at"
  | "file_name"
  | "-file_name"
  | "title"
  | "-title"
  | "file_size"
  | "-file_size";

// ---------------------------------------------------------------------------
// Dashboard types
// ---------------------------------------------------------------------------

export interface DashboardStats {
  total_departments: number;
  total_employees: number;
  total_documents: number;
}

// ---------------------------------------------------------------------------
// OCR & Text Extraction types (Milestone 6)
// ---------------------------------------------------------------------------

export interface DocumentChunk {
  id: string;
  chunk_number: number;
  content: string;
  created_at: string;
}

export interface DocumentTextResponse {
  document_id: string;
  file_name: string;
  ocr_status: string;
  total_chunks: number;
  text: string;
  chunks: DocumentChunk[];
}

export interface OCRJobData {
  job_id: string;
  document_id: string;
  status: string;
}

export interface OCRStatusData {
  job_id: string;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  result?: {
    document_id?: string;
    file_name?: string;
    total_chunks?: number;
    char_count?: number;
    error?: string;
  } | null;
}

// ---------------------------------------------------------------------------
// Semantic Search types (Milestone 7 Phase 2)
// ---------------------------------------------------------------------------

/** POST /api/v1/search request payload. */
export interface SearchRequest {
  /** Natural-language query (2–1000 characters, non-blank). */
  query: string;
  /** Maximum ranked results to return (1–20). Default: 5. */
  top_k?: number;
  /**
   * Minimum similarity threshold (0–1).
   * similarity = 1 / (1 + L2_distance). Higher = more similar.
   * Null = no threshold.
   */
  min_score?: number | null;
}

/** A single ranked search result. */
export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_name: string;
  chunk_number: number;
  content: string;
  /**
   * Raw FAISS L2 distance. Lower = more similar.
   */
  distance?: number | null;
  /**
   * Bounded similarity score: 1 / (1 + distance).
   * Range (0, 1]. Higher = more similar.
   */
  similarity?: number | null;
  /** Reciprocal Rank Fusion / reranker score. */
  score?: number | null;
  /** Match type: 'semantic' | 'lexical' | 'hybrid'. */
  match_type?: string | null;
  file_type?: string | null;
  created_at?: string;
}

/** Data payload returned inside SearchResponse. */
export interface SearchData {
  query: string;
  results: SearchResult[];
  total_results: number;
}

// ---------------------------------------------------------------------------
// AI Chat types (Milestone 7 Phase 3)
// ---------------------------------------------------------------------------

/** POST /api/v1/ai/chat request payload. */
export interface AIChatRequest {
  /** ID of a previous Q&A exchange. Ownership is verified server-side. */
  conversation_id?: string | null;
  /** Natural-language question (2–4000 characters, non-blank). */
  message: string;
  /** Maximum authorized chunks to retrieve (1–10). Default: 5. */
  top_k?: number;
  /** Minimum similarity threshold (0–1). Null = no threshold. */
  min_score?: number | null;
}

/** A single document chunk cited as a source in an AI answer. */
export interface AISource {
  chunk_id: string;
  document_id: string;
  document_name: string;
  chunk_number: number;
  content: string;
  /**
   * Bounded similarity score: 1 / (1 + L2_distance).
   * Range (0, 1]. Higher = more similar.
   */
  similarity?: number | null;
  /** Raw FAISS L2 distance. Lower = more similar. */
  distance?: number | null;
  /** Reciprocal Rank Fusion / reranker score. */
  score?: number | null;
  /** Match type: 'semantic' | 'lexical' | 'hybrid'. */
  match_type?: string | null;
}

/** Data payload returned inside AIChatResponse. */
export interface AIChatResponseData {
  /** ID of the AIConversation row created for this exchange. */
  conversation_id: string;
  /** Same as conversation_id in Phase 3 (one row = one exchange). */
  message_id: string;
  /** The AI-generated grounded answer (or deterministic fallback). */
  answer: string;
  /** Document chunks used to build the LLM context. */
  sources: AISource[];
  /** Number of authorized chunks retrieved (0 for no-context fallback). */
  retrieved_chunks: number;
}

// ---------------------------------------------------------------------------
// Dashboard types
// ---------------------------------------------------------------------------

export interface DashboardStats {
  total_departments: number;
  total_employees: number;
  total_documents: number;
  total_workflows: number;
  pending_executions: number;
}

// ---------------------------------------------------------------------------
// Workflow types (Milestone 8)
// ---------------------------------------------------------------------------

export type WorkflowActionType = "notify" | "send_email" | "archive_document" | "approve" | "delay";

export type ExecutionStatusType = "pending" | "running" | "waiting_approval" | "completed" | "failed" | "rejected";

export interface WorkflowStepCreate {
  step_number: number;
  action: WorkflowActionType;
  configuration?: Record<string, unknown> | null;
  timeout?: number | null;
  retry_count?: number;
}

export interface WorkflowStep {
  id: string;
  workflow_id: string;
  step_number: number;
  action: WorkflowActionType;
  configuration?: Record<string, unknown> | null;
  timeout?: number | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface Workflow {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  version: number;
  created_by?: string | null;
  creator_name?: string | null;
  steps: WorkflowStep[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowCreateRequest {
  name: string;
  description?: string | null;
  steps: WorkflowStepCreate[];
}

export interface WorkflowUpdateRequest {
  name?: string | null;
  description?: string | null;
  is_active?: boolean | null;
  steps?: WorkflowStepCreate[] | null;
}

export interface WorkflowRunRequest {
  context?: Record<string, unknown> | null;
}

export interface WorkflowRunResponse {
  execution_id: string;
  status: string;
}

export interface WorkflowExecutionLogStep {
  step_number: number;
  action: string;
  status: "running" | "completed" | "failed" | "requires_approval";
  started_at?: number;
  duration?: number;
  result?: Record<string, unknown>;
  error?: string;
  retries?: number;
}

export interface WorkflowExecutionLogs {
  steps?: WorkflowExecutionLogStep[];
  resume_from_step?: number;
  approval?: {
    decision: "approve" | "reject";
    approved_by: string;
    approved_at: string;
    comment?: string | null;
  };
  error?: string;
  [key: string]: unknown;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  triggered_by?: string | null;
  status: ExecutionStatusType;
  duration?: number | null;
  logs?: WorkflowExecutionLogs | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalActionRequest {
  action: "approve" | "reject";
  comment?: string | null;
}

