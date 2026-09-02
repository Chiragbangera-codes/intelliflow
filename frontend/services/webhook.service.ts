/**
 * Webhook service.
 * Provides API client calls for webhook endpoints and deliveries.
 */

import apiClient from './api';
import type {
  Webhook,
  WebhookCreatePayload,
  WebhookDelivery,
  WebhookDeliveryListResponse,
  WebhookDeliveryStatus,
  WebhookListResponse,
  WebhookUpdatePayload,
} from '@/types/webhook';

export async function getWebhooks(
  page: number = 1,
  pageSize: number = 20,
  isActive?: boolean,
): Promise<WebhookListResponse> {
  const response = await apiClient.get<WebhookListResponse>('/webhooks', {
    params: { page, page_size: pageSize, is_active: isActive },
  });
  return response.data;
}

export async function getWebhook(id: string): Promise<Webhook> {
  const response = await apiClient.get<Webhook>(`/webhooks/${id}`);
  return response.data;
}

export async function createWebhook(data: WebhookCreatePayload): Promise<Webhook> {
  const response = await apiClient.post<Webhook>('/webhooks', data);
  return response.data;
}

export async function updateWebhook(id: string, data: WebhookUpdatePayload): Promise<Webhook> {
  const response = await apiClient.patch<Webhook>(`/webhooks/${id}`, data);
  return response.data;
}

export async function deleteWebhook(id: string): Promise<void> {
  await apiClient.delete(`/webhooks/${id}`);
}

export async function testWebhook(id: string): Promise<WebhookDelivery> {
  const response = await apiClient.post<WebhookDelivery>(`/webhooks/${id}/test`);
  return response.data;
}

export async function getWebhookDeliveries(
  webhookId: string,
  page: number = 1,
  pageSize: number = 20,
  status?: WebhookDeliveryStatus,
): Promise<WebhookDeliveryListResponse> {
  const response = await apiClient.get<WebhookDeliveryListResponse>(
    `/webhooks/${webhookId}/deliveries`,
    {
      params: { page, page_size: pageSize, status },
    },
  );
  return response.data;
}
