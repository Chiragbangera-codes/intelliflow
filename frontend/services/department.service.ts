/**
 * Department service.
 *
 * Provides API client calls for department operations.
 */

import apiClient from "./api";
import type {
  ApiResponse,
  CreateDepartmentRequest,
  Department,
  UpdateDepartmentRequest,
} from "@/types";

export async function getDepartments(
  page: number = 1,
  pageSize: number = 20,
): Promise<ApiResponse<Department[]>> {
  const response = await apiClient.get<ApiResponse<Department[]>>("/departments", {
    params: { page, page_size: pageSize },
  });
  return response.data;
}

export async function getDepartment(id: string): Promise<ApiResponse<Department>> {
  const response = await apiClient.get<ApiResponse<Department>>(`/departments/${id}`);
  return response.data;
}

export async function createDepartment(
  data: CreateDepartmentRequest,
): Promise<ApiResponse<Department>> {
  const response = await apiClient.post<ApiResponse<Department>>("/departments", data);
  return response.data;
}

export async function updateDepartment(
  id: string,
  data: UpdateDepartmentRequest,
): Promise<ApiResponse<Department>> {
  const response = await apiClient.patch<ApiResponse<Department>>(`/departments/${id}`, data);
  return response.data;
}

export async function deleteDepartment(id: string): Promise<ApiResponse<void>> {
  const response = await apiClient.delete<ApiResponse<void>>(`/departments/${id}`);
  return response.data;
}
