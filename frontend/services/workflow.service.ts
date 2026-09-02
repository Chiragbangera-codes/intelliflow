/**
 * Workflow API service — Milestone 8.
 *
 * Provides API client calls for the Workflow Engine:
 *   - CRUD operations on workflows
 *   - Triggering asynchronous executions
 *   - Real-time execution status polling and history
 *   - Step approval decisions (approve / reject)
 */

import apiClient from "./api";
import type {
  ApiResponse,
  ApprovalActionRequest,
  Workflow,
  WorkflowCreateRequest,
  WorkflowExecution,
  WorkflowRunRequest,
  WorkflowRunResponse,
  WorkflowUpdateRequest,
} from "@/types";

/**
 * List workflows with pagination.
 */
export async function listWorkflows(
  page = 1,
  pageSize = 20,
): Promise<ApiResponse<Workflow[]>> {
  const response = await apiClient.get<ApiResponse<Workflow[]>>("/workflows", {
    params: { page, page_size: pageSize },
  });
  return response.data;
}

/**
 * Get a single workflow by ID with steps.
 */
export async function getWorkflow(id: string): Promise<ApiResponse<Workflow>> {
  const response = await apiClient.get<ApiResponse<Workflow>>(`/workflows/${id}`);
  return response.data;
}

/**
 * Create a new workflow definition.
 */
export async function createWorkflow(
  data: WorkflowCreateRequest,
): Promise<ApiResponse<Workflow>> {
  const response = await apiClient.post<ApiResponse<Workflow>>("/workflows", data);
  return response.data;
}

/**
 * Update an existing workflow.
 */
export async function updateWorkflow(
  id: string,
  data: WorkflowUpdateRequest,
): Promise<ApiResponse<Workflow>> {
  const response = await apiClient.put<ApiResponse<Workflow>>(`/workflows/${id}`, data);
  return response.data;
}

/**
 * Soft-delete a workflow (Admin only).
 */
export async function deleteWorkflow(id: string): Promise<ApiResponse<null>> {
  const response = await apiClient.delete<ApiResponse<null>>(`/workflows/${id}`);
  return response.data;
}

/**
 * Trigger an asynchronous workflow execution.
 */
export async function triggerWorkflow(
  id: string,
  context?: WorkflowRunRequest,
): Promise<ApiResponse<WorkflowRunResponse>> {
  const response = await apiClient.post<ApiResponse<WorkflowRunResponse>>(
    `/workflows/${id}/run`,
    context ?? {},
  );
  return response.data;
}

/**
 * List execution history for a workflow.
 */
export async function listExecutions(
  workflowId: string,
  page = 1,
  pageSize = 20,
): Promise<ApiResponse<WorkflowExecution[]>> {
  const response = await apiClient.get<ApiResponse<WorkflowExecution[]>>(
    `/workflows/${workflowId}/executions`,
    { params: { page, page_size: pageSize } },
  );
  return response.data;
}

/**
 * Get current execution status and logs (used for polling).
 */
export async function getExecution(
  executionId: string,
): Promise<ApiResponse<WorkflowExecution>> {
  const response = await apiClient.get<ApiResponse<WorkflowExecution>>(
    `/executions/${executionId}`,
  );
  return response.data;
}

/**
 * Approve or reject a workflow execution waiting at an approval step.
 */
export async function approveExecution(
  executionId: string,
  data: ApprovalActionRequest,
): Promise<ApiResponse<WorkflowExecution>> {
  const response = await apiClient.post<ApiResponse<WorkflowExecution>>(
    `/executions/${executionId}/approve`,
    data,
  );
  return response.data;
}
