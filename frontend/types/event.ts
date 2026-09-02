export type EventStatus = 'pending' | 'processing' | 'processed' | 'failed' | 'dead_letter';

export interface PlatformEvent {
  id: string;
  event_type: string;
  source: string;
  actor_id: string | null;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, unknown>;
  correlation_id: string;
  status: EventStatus;
  error_message: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface EventListResponse {
  items: PlatformEvent[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OutboxStats {
  pending: number;
  processing: number;
  processed: number;
  failed: number;
  dead_letter: number;
  total: number;
}
