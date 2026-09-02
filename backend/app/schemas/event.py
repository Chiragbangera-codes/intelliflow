"""
Event and Outbox Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.event import EventStatus


class EventResponse(BaseModel):
    """Normalized platform event item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    source: str
    actor_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    status: EventStatus
    error_message: str | None = None
    created_at: datetime
    processed_at: datetime | None = None


class EventListResponse(BaseModel):
    """Paginated list of platform events."""

    items: list[EventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class OutboxStatsResponse(BaseModel):
    """Counts of outbox events by status."""

    pending: int = 0
    processing: int = 0
    processed: int = 0
    failed: int = 0
    dead_letter: int = 0
    total: int = 0


class RetryDeadLetterRequest(BaseModel):
    """Request to retry a dead-lettered outbox event."""

    outbox_id: uuid.UUID
