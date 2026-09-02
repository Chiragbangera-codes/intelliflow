"""
Integration tests for Event Bus and Transactional Outbox pattern.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import EventStatus
from app.models.user import User
from app.services.event_bus_service import EventBusService


@pytest.mark.asyncio
class TestEventBusAndOutbox:
    """Test Event publication, Outbox pattern, and Events API endpoints."""

    async def test_publish_event_atomic_outbox(self, db_session: AsyncSession) -> None:
        """Verify that publish_event commits both normalized event and outbox record."""
        service = EventBusService(db_session)
        event, outbox = await service.publish_event(
            event_type="document.created",
            source="test_service",
            payload={"document_id": "doc_123", "title": "Quarterly Report"},
            correlation_id=str(uuid.uuid4()),
        )

        assert event.id is not None
        assert event.event_type == "document.created"
        assert event.payload["title"] == "Quarterly Report"

        assert outbox.id is not None
        assert outbox.event_id == event.id
        assert outbox.status == EventStatus.PENDING

    async def test_process_outbox_batch(self, db_session: AsyncSession) -> None:
        """Verify that process_outbox_batch drains pending events."""
        service = EventBusService(db_session)
        event, outbox = await service.publish_event(
            event_type="employee.onboarded",
            source="hr_service",
            payload={"employee_id": "emp_999"},
        )

        # Process outbox
        results = await service.process_outbox_batch(limit=10)
        assert results["processed"] >= 1

        # Re-fetch outbox
        updated_outbox = await service.outbox_repo.get_by_id(outbox.id)
        assert updated_outbox is not None
        assert updated_outbox.status == EventStatus.PROCESSED
        assert updated_outbox.processed_at is not None

    async def test_events_api_list_and_get(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
        admin_user: User,
    ) -> None:
        """Verify GET /api/v1/events and GET /api/v1/events/{id} endpoints."""
        service = EventBusService(db_session)
        corr_id = f"corr-{uuid.uuid4().hex[:8]}"
        event, _ = await service.publish_event(
            event_type="workflow.started",
            source="workflow_engine",
            payload={"workflow_id": "wf_1"},
            correlation_id=corr_id,
            actor_id=admin_user.id,
        )

        # List events
        res = await async_client.get(
            "/api/v1/events",
            params={"correlation_id": corr_id},
            headers=admin_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert data["items"][0]["event_type"] == "workflow.started"

        # Get single event
        get_res = await async_client.get(
            f"/api/v1/events/{event.id}",
            headers=admin_headers,
        )
        assert get_res.status_code == 200
        event_data = get_res.json()
        assert event_data["id"] == str(event.id)
        assert event_data["payload"]["workflow_id"] == "wf_1"

    async def test_outbox_stats_and_retry(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        """Verify GET /api/v1/events/outbox/stats and POST /api/v1/events/outbox/retry."""
        service = EventBusService(db_session)
        _, outbox = await service.publish_event(
            event_type="test.deadletter",
            source="test",
            payload={"info": "sample"},
        )

        # Force dead-letter status
        outbox.status = EventStatus.DEAD_LETTER
        outbox.retry_count = 5
        outbox.error_message = "Max retries exceeded"
        await db_session.commit()

        # Check stats
        stats_res = await async_client.get(
            "/api/v1/events/outbox/stats",
            headers=admin_headers,
        )
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["dead_letter"] >= 1

        # Retry dead-letter event
        retry_res = await async_client.post(
            "/api/v1/events/outbox/retry",
            json={"outbox_id": str(outbox.id)},
            headers=admin_headers,
        )
        assert retry_res.status_code == 200

        # Verify status reset to pending
        await db_session.refresh(outbox)
        assert outbox.status == EventStatus.PENDING
        assert outbox.retry_count == 0
