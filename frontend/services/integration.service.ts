/**
 * Integration service.
 * Provides API client calls for external integrations management.
 */

import apiClient from './api';
import type {
  Integration,
  IntegrationCreatePayload,
  IntegrationListResponse,
  IntegrationProvider,
  IntegrationStatus,
  IntegrationTestResult,
  IntegrationUpdatePayload,
} from '@/types/integration';

export async function getIntegrations(
  page: number = 1,
  pageSize: number = 20,
  provider?: IntegrationProvider,
  status?: IntegrationStatus,
): Promise<IntegrationListResponse> {
  const response = await apiClient.get<IntegrationListResponse>('/integrations', {
    params: { page, page_size: pageSize, provider, status },
  });
  return response.data;
}

export async function getIntegration(id: string): Promise<Integration> {
  const response = await apiClient.get<Integration>(`/integrations/${id}`);
  return response.data;
}

export async function createIntegration(data: IntegrationCreatePayload): Promise<Integration> {
  const response = await apiClient.post<Integration>('/integrations', data);
  return response.data;
}

export async function updateIntegration(
  id: string,
  data: IntegrationUpdatePayload,
): Promise<Integration> {
  const response = await apiClient.patch<Integration>(`/integrations/${id}`, data);
  return response.data;
}

export async function deleteIntegration(id: string): Promise<void> {
  await apiClient.delete(`/integrations/${id}`);
}

export async function testIntegration(id: string): Promise<IntegrationTestResult> {
  const response = await apiClient.post<IntegrationTestResult>(`/integrations/${id}/test`);
  return response.data;
}
