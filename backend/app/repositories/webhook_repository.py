"""
Webhook and WebhookDelivery repository.

Provides database operations for managing webhook endpoints and tracking delivery logs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook, WebhookDelivery, WebhookDeliveryStatus


class WebhookRepository:
    """Repository for Webhooks and WebhookDeliveries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_webhook(
        self,
        name: str,
        url: str,
        secret: str,
        subscribed_events: list[str],
        description: str | None = None,
        is_active: bool = True,
        created_by: uuid.UUID | None = None,
    ) -> Webhook:
        """Create and persist a new webhook endpoint."""
        webhook = Webhook(
            name=name,
            url=url,
            secret=secret,
            subscribed_events=subscribed_events,
            description=description,
            is_active=is_active,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(webhook)
        await self.session.flush()
        return webhook

    async def get_by_id(self, webhook_id: uuid.UUID) -> Webhook | None:
        """Get a webhook by its ID."""
        stmt = select(Webhook).where(Webhook.id == webhook_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_webhooks(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
    ) -> tuple[list[Webhook], int]:
        """List webhooks with optional status filter and pagination."""
        stmt = select(Webhook)
        count_stmt = select(func.count(Webhook.id))

        if is_active is not None:
            stmt = stmt.where(Webhook.is_active == is_active)
            count_stmt = count_stmt.where(Webhook.is_active == is_active)

        total_res = await self.session.execute(count_stmt)
        total_items = total_res.scalar() or 0

        stmt = (
            stmt.order_by(Webhook.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        items_res = await self.session.execute(stmt)
        webhooks = list(items_res.scalars().all())

        return webhooks, total_items

    async def update_webhook(
        self,
        webhook_id: uuid.UUID,
        name: str | None = None,
        url: str | None = None,
        secret: str | None = None,
        subscribed_events: list[str] | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Webhook | None:
        """Update webhook endpoint properties."""
        webhook = await self.get_by_id(webhook_id)
        if not webhook:
            return None

        if name is not None:
            webhook.name = name
        if url is not None:
            webhook.url = url
        if secret is not None:
            webhook.secret = secret
        if subscribed_events is not None:
            webhook.subscribed_events = subscribed_events
        if description is not None:
            webhook.description = description
        if is_active is not None:
            webhook.is_active = is_active

        webhook.updated_at = datetime.now(UTC)
        await self.session.flush()
        return webhook

    async def delete_webhook(self, webhook_id: uuid.UUID) -> bool:
        """Delete a webhook and cascade-delete delivery history."""
        webhook = await self.get_by_id(webhook_id)
        if not webhook:
            return False
        await self.session.delete(webhook)
        await self.session.flush()
        return True

    async def find_matching_webhooks(self, event_type: str) -> list[Webhook]:
        """
        Find active webhooks subscribed to the given event type or wildcard '*'.
        """
        stmt = select(Webhook).where(Webhook.is_active.is_(True))
        res = await self.session.execute(stmt)
        all_active = res.scalars().all()

        matched: list[Webhook] = []
        for wh in all_active:
            subs = wh.subscribed_events or []
            if "*" in subs or event_type in subs:
                matched.append(wh)
        return matched

    async def update_last_delivery_at(
        self, webhook_id: uuid.UUID, timestamp: datetime | None = None
    ) -> None:
        """Update the last_delivery_at timestamp on a webhook."""
        webhook = await self.get_by_id(webhook_id)
        if webhook:
            webhook.last_delivery_at = timestamp or datetime.now(UTC)
            await self.session.flush()

    # -------------------------------------------------------------------------
    # Webhook Deliveries
    # -------------------------------------------------------------------------
    async def create_delivery(
        self,
        webhook_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
        event_id: uuid.UUID | None = None,
        request_headers: dict[str, str] | None = None,
        response_status_code: int | None = None,
        response_body: str | None = None,
        response_headers: dict[str, str] | None = None,
        duration_ms: int | None = None,
        status: WebhookDeliveryStatus = WebhookDeliveryStatus.PENDING,
        attempt_count: int = 1,
        error_message: str | None = None,
    ) -> WebhookDelivery:
        """Record a webhook delivery attempt."""
        delivery = WebhookDelivery(
            webhook_id=webhook_id,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            request_headers=request_headers,
            response_status_code=response_status_code,
            response_body=response_body,
            response_headers=response_headers,
            duration_ms=duration_ms,
            status=status,
            attempt_count=attempt_count,
            error_message=error_message,
            created_at=datetime.now(UTC),
            delivered_at=datetime.now(UTC) if status == WebhookDeliveryStatus.SUCCESS else None,
        )
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def list_deliveries(
        self,
        webhook_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        status: WebhookDeliveryStatus | None = None,
    ) -> tuple[list[WebhookDelivery], int]:
        """List delivery history with optional filtering and pagination."""
        stmt = select(WebhookDelivery)
        count_stmt = select(func.count(WebhookDelivery.id))

        if webhook_id is not None:
            stmt = stmt.where(WebhookDelivery.webhook_id == webhook_id)
            count_stmt = count_stmt.where(WebhookDelivery.webhook_id == webhook_id)
        if status is not None:
            stmt = stmt.where(WebhookDelivery.status == status)
            count_stmt = count_stmt.where(WebhookDelivery.status == status)

        total_res = await self.session.execute(count_stmt)
        total_items = total_res.scalar() or 0

        stmt = (
            stmt.order_by(WebhookDelivery.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items_res = await self.session.execute(stmt)
        deliveries = list(items_res.scalars().all())

        return deliveries, total_items
