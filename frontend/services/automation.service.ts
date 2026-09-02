/**
 * Automation service.
 * Provides API client calls for automation rules and executions.
 */

import apiClient from './api';
import type {
  AutomationExecutionListResponse,
  AutomationRule,
  AutomationRuleCreatePayload,
  AutomationRuleListResponse,
  AutomationRuleUpdatePayload,
  AutomationStatus,
  AutomationTestResult,
} from '@/types/automation';

export async function getAutomationRules(
  page: number = 1,
  pageSize: number = 20,
  triggerEvent?: string,
  isActive?: boolean,
): Promise<AutomationRuleListResponse> {
  const response = await apiClient.get<AutomationRuleListResponse>('/automations', {
    params: { page, page_size: pageSize, trigger_event: triggerEvent, is_active: isActive },
  });
  return response.data;
}

export async function getAutomationRule(id: string): Promise<AutomationRule> {
  const response = await apiClient.get<AutomationRule>(`/automations/${id}`);
  return response.data;
}

export async function createAutomationRule(
  data: AutomationRuleCreatePayload,
): Promise<AutomationRule> {
  const response = await apiClient.post<AutomationRule>('/automations', data);
  return response.data;
}

export async function updateAutomationRule(
  id: string,
  data: AutomationRuleUpdatePayload,
): Promise<AutomationRule> {
  const response = await apiClient.patch<AutomationRule>(`/automations/${id}`, data);
  return response.data;
}

export async function deleteAutomationRule(id: string): Promise<void> {
  await apiClient.delete(`/automations/${id}`);
}

export async function getAutomationExecutions(
  ruleId: string,
  page: number = 1,
  pageSize: number = 20,
  status?: AutomationStatus,
): Promise<AutomationExecutionListResponse> {
  const response = await apiClient.get<AutomationExecutionListResponse>(
    `/automations/${ruleId}/executions`,
    {
      params: { page, page_size: pageSize, status },
    },
  );
  return response.data;
}

export async function testAutomationRule(
  id: string,
  eventContext: Record<string, unknown>,
): Promise<AutomationTestResult> {
  const response = await apiClient.post<AutomationTestResult>(`/automations/${id}/test`, {
    event_context: eventContext,
  });
  return response.data;
}
