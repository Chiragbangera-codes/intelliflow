"""
Event and Outbox repositories.

Handles database operations for normalized Event logs and Transactional Outbox queues.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventStatus, OutboxEvent


class EventRepository:
    """Repository for querying normalized platform events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        event_type: str,
        payload: dict[str, Any],
        actor_id: uuid.UUID | None = None,
        source: str = "intelliflow.core",
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        status: EventStatus = EventStatus.PROCESSED,
        error_message: str | None = None,
    ) -> Event:
        """Create and persist a new Event record."""
        event = Event(
            event_type=event_type,
            source=source,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4()),
            status=status,
            error_message=error_message,
            created_at=datetime.now(UTC),
            processed_at=datetime.now(UTC) if status == EventStatus.PROCESSED else None,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: uuid.UUID) -> Event | None:
        """Fetch a single event by ID."""
        stmt = select(Event).where(Event.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_events(
        self,
        page: int = 1,
        page_size: int = 20,
        event_type: str | None = None,
        source: str | None = None,
        actor_id: uuid.UUID | None = None,
        correlation_id: str | None = None,
        status: EventStatus | None = None,
    ) -> tuple[list[Event], int]:
        """List events with optional filtering and pagination."""
        stmt = select(Event)
        count_stmt = select(func.count(Event.id))

        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
            count_stmt = count_stmt.where(Event.event_type == event_type)
        if source:
            stmt = stmt.where(Event.source == source)
            count_stmt = count_stmt.where(Event.source == source)
        if actor_id:
            stmt = stmt.where(Event.actor_id == actor_id)
            count_stmt = count_stmt.where(Event.actor_id == actor_id)
        if correlation_id:
            stmt = stmt.where(Event.correlation_id == correlation_id)
            count_stmt = count_stmt.where(Event.correlation_id == correlation_id)
        if status:
            stmt = stmt.where(Event.status == status)
            count_stmt = count_stmt.where(Event.status == status)

        total_res = await self.session.execute(count_stmt)
        total_items = total_res.scalar() or 0

        stmt = (
            stmt.order_by(Event.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        items_res = await self.session.execute(stmt)
        events = list(items_res.scalars().all())

        return events, total_items


class OutboxRepository:
    """Repository for Transactional Outbox pattern."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        event_type: str,
        payload: dict[str, Any],
        actor_id: uuid.UUID | None = None,
        source: str = "intelliflow.core",
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        max_retries: int = 5,
    ) -> OutboxEvent:
        """Create and queue a new OutboxEvent record."""
        outbox = OutboxEvent(
            event_type=event_type,
            source=source,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4()),
            status=EventStatus.PENDING,
            retry_count=0,
            max_retries=max_retries,
            created_at=datetime.now(UTC),
        )
        self.session.add(outbox)
        await self.session.flush()
        return outbox

    async def get_by_id(self, outbox_id: uuid.UUID) -> OutboxEvent | None:
        """Fetch an outbox event by ID."""
        return await self.session.get(OutboxEvent, outbox_id)

    async def fetch_pending_events(self, limit: int = 50) -> list[OutboxEvent]:
        """
        Fetch pending or retryable outbox events.
        """
        now = datetime.now(UTC)
        stmt = (
            select(OutboxEvent)
            .where(
                (OutboxEvent.status == EventStatus.PENDING)
                | (
                    (OutboxEvent.status == EventStatus.FAILED)
                    & (OutboxEvent.next_retry_at <= now)
                    & (OutboxEvent.retry_count < OutboxEvent.max_retries)
                )
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_processing(self, outbox_id: uuid.UUID) -> None:
        """Mark an outbox event as currently processing."""
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == outbox_id)
            .values(status=EventStatus.PROCESSING)
        )
        await self.session.execute(stmt)

    async def mark_processed(self, outbox_id: uuid.UUID) -> None:
        """Mark an outbox event as successfully processed."""
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == outbox_id)
            .values(
                status=EventStatus.PROCESSED,
                processed_at=datetime.now(UTC),
                last_error=None,
            )
        )
        await self.session.execute(stmt)

    async def mark_failed(
        self,
        outbox_id: uuid.UUID,
        error_message: str,
        backoff_factor: float = 2.0,
    ) -> None:
        """Record an outbox processing failure and schedule retry or dead-letter."""
        outbox = await self.session.get(OutboxEvent, outbox_id)
        if not outbox:
            return

        outbox.retry_count += 1
        outbox.last_error = error_message

        if outbox.retry_count >= outbox.max_retries:
            outbox.status = EventStatus.DEAD_LETTER
            outbox.next_retry_at = None
        else:
            outbox.status = EventStatus.FAILED
            delay_seconds = int(5 * (backoff_factor ** (outbox.retry_count - 1)))
            outbox.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

        await self.session.flush()

    async def retry_dead_letter(self, outbox_id: uuid.UUID) -> OutboxEvent | None:
        """Reset a dead-lettered outbox event to pending for re-attempt."""
        outbox = await self.session.get(OutboxEvent, outbox_id)
        if not outbox or outbox.status != EventStatus.DEAD_LETTER:
            return None

        outbox.status = EventStatus.PENDING
        outbox.retry_count = 0
        outbox.next_retry_at = None
        outbox.last_error = None
        await self.session.flush()
        return outbox

    async def get_outbox_stats(self) -> dict[str, int]:
        """Return counts of outbox events by status."""
        stmt = select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(OutboxEvent.status)
        res = await self.session.execute(stmt)
        counts = {status.value: 0 for status in EventStatus}
        for status_val, count in res.all():
            counts[status_val.value] = count
        return counts
