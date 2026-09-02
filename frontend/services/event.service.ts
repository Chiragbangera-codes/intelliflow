/**
 * Event and Outbox service.
 * Provides API client calls for platform events and outbox telemetry.
 */

import apiClient from './api';
import type { EventListResponse, EventStatus, OutboxStats, PlatformEvent } from '@/types/event';

export async function getEvents(
  page: number = 1,
  pageSize: number = 20,
  eventType?: string,
  source?: string,
  correlationId?: string,
  status?: EventStatus,
): Promise<EventListResponse> {
  const response = await apiClient.get<EventListResponse>('/events', {
    params: {
      page,
      page_size: pageSize,
      event_type: eventType,
      source,
      correlation_id: correlationId,
      status,
    },
  });
  return response.data;
}

export async function getEvent(id: string): Promise<PlatformEvent> {
  const response = await apiClient.get<PlatformEvent>(`/events/${id}`);
  return response.data;
}

export async function getOutboxStats(): Promise<OutboxStats> {
  const response = await apiClient.get<OutboxStats>('/events/outbox/stats');
  return response.data;
}

export async function retryDeadLetterEvent(outboxId: string): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>('/events/outbox/retry', {
    outbox_id: outboxId,
  });
  return response.data;
}
