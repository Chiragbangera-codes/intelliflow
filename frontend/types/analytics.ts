/**
 * Phase 9 — Analytics, Predictions, and Reports TypeScript types.
 *
 * Mirrors the backend Pydantic schemas exactly so the compiler catches
 * any API contract drift at build time.
 */

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

export interface MonthlyCount {
  month: string;
  count: number;
}

export interface MonthlyRevenue {
  month: string;
  revenue: number;
  expenses: number;
  profit: number;
}

export interface RoleCount {
  role: string;
  count: number;
}

export interface StatusCount {
  status: string;
  count: number;
}

// ---------------------------------------------------------------------------
// KPI Summary
// ---------------------------------------------------------------------------

export interface KPISummary {
  total_employees: number;
  total_documents: number;
  active_workflows: number;
  total_ai_conversations: number;
  completed_workflow_executions: number;
  total_predictions_run: number;
  total_reports_generated: number;
}

// ---------------------------------------------------------------------------
// Revenue Analytics
// ---------------------------------------------------------------------------

export interface RevenueAnalytics {
  year: number;
  data: MonthlyRevenue[];
  total_expenses_ytd: number;
  avg_monthly_expenses: number;
}

// ---------------------------------------------------------------------------
// Department Analytics
// ---------------------------------------------------------------------------

export interface DepartmentAnalyticsItem {
  department_id: string;
  department_name: string;
  employee_count: number;
  avg_salary: number;
  document_count: number;
  active_workflows: number;
}

export interface DepartmentAnalytics {
  data: DepartmentAnalyticsItem[];
  total_departments: number;
}

// ---------------------------------------------------------------------------
// Employee Analytics
// ---------------------------------------------------------------------------

export interface EmployeeAnalytics {
  total: number;
  active: number;
  new_this_month: number;
  role_distribution: RoleCount[];
  monthly_headcount: MonthlyCount[];
}

// ---------------------------------------------------------------------------
// Document Analytics
// ---------------------------------------------------------------------------

export interface DocumentAnalytics {
  total_uploads: number;
  monthly_uploads: MonthlyCount[];
  by_status: StatusCount[];
  by_ocr_status: StatusCount[];
}

// ---------------------------------------------------------------------------
// Workflow Analytics
// ---------------------------------------------------------------------------

export interface WorkflowAnalytics {
  total_executions: number;
  by_status: StatusCount[];
  avg_duration_seconds: number;
  step_action_frequency: StatusCount[];
}

// ---------------------------------------------------------------------------
// AI Usage Analytics
// ---------------------------------------------------------------------------

export interface AIUsageAnalytics {
  total_conversations: number;
  monthly_conversations: MonthlyCount[];
  avg_response_time_seconds: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
}

// ---------------------------------------------------------------------------
// Predictions
// ---------------------------------------------------------------------------

export type PredictionModelName =
  | "revenue_forecast"
  | "employee_attrition"
  | "customer_churn";

export interface PredictionRequest {
  model: PredictionModelName;
  input?: Record<string, unknown>;
}

export interface Prediction {
  id: string;
  model: string;
  input?: Record<string, unknown> | null;
  prediction?: Record<string, unknown> | null;
  confidence?: number | null;
  execution_time?: number | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export type ReportTypeName =
  | "revenue"
  | "employees"
  | "departments"
  | "workflows"
  | "documents"
  | "ai_usage";

export type ReportFormatName = "csv" | "xlsx" | "pdf";

export type ReportStatus = "pending" | "completed" | "failed";

export interface ReportGenerateRequest {
  report_type: ReportTypeName;
  format?: ReportFormatName;
  filters?: Record<string, unknown>;
}

export interface Report {
  id: string;
  report_type: string;
  format?: string | null;
  status: ReportStatus;
  file_path?: string | null;
  generated_by?: string | null;
  generated_at?: string | null;
  created_at: string;
  updated_at: string;
}
