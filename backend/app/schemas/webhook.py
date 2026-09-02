"""
Webhook and WebhookDelivery Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.webhook import WebhookDeliveryStatus


class WebhookCreate(BaseModel):
    """Payload to register a new webhook endpoint."""

    name: str = Field(..., min_length=2, max_length=150)
    url: str = Field(..., min_length=8, max_length=2048)
    subscribed_events: list[str] = Field(default_factory=lambda: ["*"])
    description: str | None = Field(default=None, max_length=500)
    secret: str | None = Field(default=None, min_length=8, max_length=255)
    is_active: bool = True


class WebhookUpdate(BaseModel):
    """Payload to update an existing webhook."""

    name: str | None = Field(default=None, min_length=2, max_length=150)
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    subscribed_events: list[str] | None = None
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    rotate_secret: bool = False


class WebhookResponse(BaseModel):
    """Webhook details with masked secret."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    url: str
    masked_secret: str
    is_active: bool
    subscribed_events: list[str]
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    last_delivery_at: datetime | None = None


class WebhookCreateResponse(WebhookResponse):
    """Returned on creation or secret rotation with one-time plaintext secret."""

    plaintext_secret: str | None = None


class WebhookListResponse(BaseModel):
    """Paginated list of webhooks."""

    items: list[WebhookResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery attempt record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    webhook_id: uuid.UUID
    event_id: uuid.UUID | None = None
    event_type: str
    payload: dict[str, Any]
    request_headers: dict[str, str] | None = None
    response_status_code: int | None = None
    response_body: str | None = None
    response_headers: dict[str, str] | None = None
    duration_ms: int | None = None
    status: WebhookDeliveryStatus
    attempt_count: int
    error_message: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None


class WebhookDeliveryListResponse(BaseModel):
    """Paginated list of webhook delivery attempts."""

    items: list[WebhookDeliveryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
