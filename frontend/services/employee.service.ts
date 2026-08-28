/**
 * Employee profile service.
 *
 * Provides API client calls for employee profile operations.
 */

import apiClient from "./api";
import type {
  ApiResponse,
  CreateEmployeeProfileRequest,
  EmployeeProfile,
  UpdateEmployeeProfileRequest,
} from "@/types";

export async function getEmployees(
  page: number = 1,
  pageSize: number = 20,
): Promise<ApiResponse<EmployeeProfile[]>> {
  const response = await apiClient.get<ApiResponse<EmployeeProfile[]>>("/employees", {
    params: { page, page_size: pageSize },
  });
  return response.data;
}

export async function getEmployeeProfile(
  userId: string,
): Promise<ApiResponse<EmployeeProfile>> {
  const response = await apiClient.get<ApiResponse<EmployeeProfile>>(
    `/employees/${userId}/profile`,
  );
  return response.data;
}

export async function createEmployeeProfile(
  userId: string,
  data: CreateEmployeeProfileRequest,
): Promise<ApiResponse<EmployeeProfile>> {
  const response = await apiClient.post<ApiResponse<EmployeeProfile>>(
    `/employees/${userId}/profile`,
    data,
  );
  return response.data;
}

export async function updateEmployeeProfile(
  userId: string,
  data: UpdateEmployeeProfileRequest,
): Promise<ApiResponse<EmployeeProfile>> {
  const response = await apiClient.patch<ApiResponse<EmployeeProfile>>(
    `/employees/${userId}/profile`,
    data,
  );
  return response.data;
}
