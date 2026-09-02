export type WebhookDeliveryStatus = 'pending' | 'success' | 'failed';

export interface Webhook {
  id: string;
  name: string;
  description: string | null;
  url: string;
  masked_secret: string;
  is_active: boolean;
  subscribed_events: string[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
  last_delivery_at: string | null;
  plaintext_secret?: string | null;
}

export interface WebhookCreatePayload {
  name: string;
  url: string;
  subscribed_events?: string[];
  description?: string | null;
  secret?: string | null;
  is_active?: boolean;
}

export interface WebhookUpdatePayload {
  name?: string | null;
  url?: string | null;
  subscribed_events?: string[] | null;
  description?: string | null;
  is_active?: boolean | null;
  rotate_secret?: boolean;
}

export interface WebhookListResponse {
  items: Webhook[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  event_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  request_headers: Record<string, string> | null;
  response_status_code: number | null;
  response_body: string | null;
  response_headers: Record<string, string> | null;
  duration_ms: number | null;
  status: WebhookDeliveryStatus;
  attempt_count: number;
  error_message: string | null;
  created_at: string;
  delivered_at: string | null;
}

export interface WebhookDeliveryListResponse {
  items: WebhookDelivery[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
