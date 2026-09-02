"""
Event Bus Service and Transactional Outbox processor.

Provides centralized event publishing within active database transactions,
and reliable background outbox batch draining to Celery event handlers.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventStatus, OutboxEvent
from app.repositories.event_repository import EventRepository, OutboxRepository

logger = logging.getLogger(__name__)


class EventBusService:
    """Centralized service for publishing events and draining the transactional outbox."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.event_repo = EventRepository(session)
        self.outbox_repo = OutboxRepository(session)

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        actor_id: uuid.UUID | None = None,
        source: str = "intelliflow.core",
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        max_retries: int = 5,
        trigger_worker: bool = True,
    ) -> OutboxEvent:
        """
        Publish an event by queuing it into the transactional outbox.
        Ensures the event is committed atomically alongside business records.
        """
        outbox_event = await self.outbox_repo.create(
            event_type=event_type,
            payload=payload,
            actor_id=actor_id,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            max_retries=max_retries,
        )

        logger.info(
            "Event queued in outbox: id=%s type=%s correlation_id=%s",
            outbox_event.id,
            event_type,
            outbox_event.correlation_id,
        )

        # Trigger worker immediately after commit if requested
        if trigger_worker:
            try:
                from app.workers.celery_app import celery_app

                celery_app.send_task("app.workers.event_tasks.process_outbox_batch_task")
            except Exception as exc:
                logger.debug("Could not dispatch async outbox task immediately: %s", exc)

        return outbox_event

    async def publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        actor_id: uuid.UUID | None = None,
        source: str = "intelliflow.core",
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        max_retries: int = 5,
        trigger_worker: bool = False,
    ) -> tuple[Event, OutboxEvent]:
        """Publish normalized event directly and queue outbox entry atomically."""
        corr = correlation_id or f"corr-{uuid.uuid4().hex[:12]}"
        event = await self.event_repo.create(
            event_type=event_type,
            payload=payload,
            actor_id=actor_id,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=corr,
            status=EventStatus.PENDING,
        )
        outbox = await self.outbox_repo.create(
            event_type=event_type,
            payload=payload,
            actor_id=actor_id,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=corr,
            max_retries=max_retries,
        )
        outbox.event_id = event.id
        await self.session.commit()
        return event, outbox

    async def process_outbox_batch(self, limit: int = 50) -> dict[str, int]:
        """
        Fetch pending outbox records, persist normalized Event logs, and trigger dispatching.

        Returns:
            Dict summarizing count of processed, failed, and dead_letter events.
        """
        pending = await self.outbox_repo.fetch_pending_events(limit=limit)
        results = {"total": len(pending), "processed": 0, "failed": 0, "dead_letter": 0}

        for item in pending:
            await self.outbox_repo.mark_processing(item.id)
            await self.session.commit()

            try:
                # 1. Create normalized Event record
                event = await self.event_repo.create(
                    event_type=item.event_type,
                    payload=item.payload,
                    actor_id=item.actor_id,
                    source=item.source,
                    entity_type=item.entity_type,
                    entity_id=item.entity_id,
                    correlation_id=item.correlation_id,
                    status=EventStatus.PROCESSED,
                )

                # 2. Dispatch event to automations and webhooks
                try:
                    from app.workers.celery_app import celery_app

                    celery_app.send_task(
                        "app.workers.event_tasks.dispatch_event_task",
                        kwargs={
                            "event_id": str(event.id),
                            "event_type": event.event_type,
                            "payload": event.payload,
                            "correlation_id": event.correlation_id,
                            "actor_id": str(event.actor_id) if event.actor_id else None,
                        },
                    )
                except Exception as dispatch_err:
                    logger.warning(
                        "Failed to queue dispatch_event_task for event %s: %s",
                        event.id,
                        dispatch_err,
                    )

                # 3. Mark outbox record processed
                await self.outbox_repo.mark_processed(item.id)
                await self.session.commit()
                results["processed"] += 1

            except Exception as exc:
                logger.exception("Error processing outbox event %s: %s", item.id, exc)
                await self.session.rollback()
                await self.outbox_repo.mark_failed(item.id, error_message=str(exc))
                await self.session.commit()

                refreshed = await self.session.get(OutboxEvent, item.id)
                if refreshed and refreshed.status == EventStatus.DEAD_LETTER:
                    results["dead_letter"] += 1
                else:
                    results["failed"] += 1

        return results

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
        """Query historical events."""
        return await self.event_repo.list_events(
            page=page,
            page_size=page_size,
            event_type=event_type,
            source=source,
            actor_id=actor_id,
            correlation_id=correlation_id,
            status=status,
        )

    async def get_event_by_id(self, event_id: uuid.UUID) -> Event | None:
        """Fetch an event by ID."""
        return await self.event_repo.get_by_id(event_id)

    async def get_outbox_stats(self) -> dict[str, int]:
        """Get outbox queue statistics."""
        return await self.outbox_repo.get_outbox_stats()

    async def retry_dead_letter(self, outbox_id: uuid.UUID) -> OutboxEvent | None:
        """Reset a dead-letter outbox event to pending status."""
        item = await self.outbox_repo.retry_dead_letter(outbox_id)
        if item:
            await self.session.commit()
        return item
