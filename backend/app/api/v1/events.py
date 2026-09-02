"""
Events and Outbox API endpoints.

Endpoints:
  GET  /api/v1/events                     — List normalized events
  GET  /api/v1/events/outbox/stats        — Get outbox health metrics
  POST /api/v1/events/outbox/retry        — Retry dead-lettered outbox event
  GET  /api/v1/events/{id}                — Get event details
"""

from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.event import EventStatus
from app.models.user import User
from app.schemas.event import (
    EventListResponse,
    EventResponse,
    OutboxStatsResponse,
    RetryDeadLetterRequest,
)
from app.services.event_bus_service import EventBusService

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=EventListResponse)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: str | None = Query(None),
    source: str | None = Query(None),
    correlation_id: str | None = Query(None),
    status_filter: EventStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> EventListResponse:
    """List historical platform events (admin and manager)."""
    service = EventBusService(db)
    items, total = await service.list_events(
        page=page,
        page_size=page_size,
        event_type=event_type,
        source=source,
        correlation_id=correlation_id,
        status=status_filter,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/outbox/stats", response_model=OutboxStatsResponse)
async def get_outbox_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> OutboxStatsResponse:
    """Get transactional outbox queue statistics (admin and manager)."""
    service = EventBusService(db)
    stats_dict = await service.get_outbox_stats()
    total = sum(stats_dict.values())
    return OutboxStatsResponse(
        pending=stats_dict.get("pending", 0),
        processing=stats_dict.get("processing", 0),
        processed=stats_dict.get("processed", 0),
        failed=stats_dict.get("failed", 0),
        dead_letter=stats_dict.get("dead_letter", 0),
        total=total,
    )


@router.post("/outbox/retry", status_code=status.HTTP_200_OK)
async def retry_dead_letter(
    payload: RetryDeadLetterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Retry a dead-letter outbox event (admin only)."""
    service = EventBusService(db)
    retried = await service.retry_dead_letter(payload.outbox_id)
    if not retried:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outbox event not found or is not in dead_letter status.",
        )
    return {"message": "Outbox event reset to pending for retry."}


@router.get("/{id}", response_model=EventResponse)
async def get_event(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> EventResponse:
    """Get event details by ID (admin and manager)."""
    service = EventBusService(db)
    event = await service.get_event_by_id(id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )
    return EventResponse.model_validate(event)
