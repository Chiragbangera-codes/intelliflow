"""
Webhooks API endpoints.

Endpoints:
  GET    /api/v1/webhooks                 — List webhooks
  POST   /api/v1/webhooks                 — Create a webhook
  GET    /api/v1/webhooks/{id}            — Get webhook details
  PATCH  /api/v1/webhooks/{id}            — Update webhook configuration
  DELETE /api/v1/webhooks/{id}            — Delete a webhook
  POST   /api/v1/webhooks/{id}/test       — Dispatch a test ping
  GET    /api/v1/webhooks/{id}/deliveries — List delivery logs
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.user import User
from app.models.webhook import WebhookDeliveryStatus
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreateResponse,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
    WebhookListResponse,
    WebhookResponse,
    WebhookUpdate,
)
from app.services.webhook_service import WebhookService, mask_secret
from app.utils.ssrf import SSRFValidationError

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _to_response(webhook: Any) -> WebhookResponse:
    """Helper to transform ORM webhook into schema with masked secret."""
    return WebhookResponse(
        id=webhook.id,
        name=webhook.name,
        description=webhook.description,
        url=webhook.url,
        masked_secret=mask_secret(webhook.secret),
        is_active=webhook.is_active,
        subscribed_events=webhook.subscribed_events or ["*"],
        created_by=webhook.created_by,
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
        last_delivery_at=webhook.last_delivery_at,
    )


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> WebhookListResponse:
    """List registered webhooks (admin and manager)."""
    service = WebhookService(db)
    items, total = await service.list_webhooks(page=page, page_size=page_size, is_active=is_active)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return WebhookListResponse(
        items=[_to_response(w) for w in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=WebhookCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> WebhookCreateResponse:
    """Create a new webhook endpoint and receive the signing secret (admin only)."""
    service = WebhookService(db)
    try:
        webhook, plain_secret = await service.create_webhook(
            name=payload.name,
            url=payload.url,
            subscribed_events=payload.subscribed_events,
            description=payload.description,
            secret=payload.secret,
            is_active=payload.is_active,
            created_by=current_user.id,
        )
    except SSRFValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SSRF Security Violation: {err}",
        ) from err

    resp = _to_response(webhook)
    return WebhookCreateResponse(
        **resp.model_dump(),
        plaintext_secret=plain_secret,
    )


@router.get("/{id}", response_model=WebhookResponse)
async def get_webhook(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> WebhookResponse:
    """Get webhook details (admin and manager)."""
    service = WebhookService(db)
    webhook = await service.get_by_id(id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found.",
        )
    return _to_response(webhook)


@router.patch("/{id}", response_model=WebhookCreateResponse)
async def update_webhook(
    id: uuid.UUID,
    payload: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> WebhookCreateResponse:
    """Update webhook endpoint properties or rotate signing secret (admin only)."""
    service = WebhookService(db)
    try:
        updated, new_secret = await service.update_webhook(
            webhook_id=id,
            name=payload.name,
            url=payload.url,
            subscribed_events=payload.subscribed_events,
            description=payload.description,
            is_active=payload.is_active,
            rotate_secret=payload.rotate_secret,
        )
    except SSRFValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SSRF Security Violation: {err}",
        ) from err

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found.",
        )

    resp = _to_response(updated)
    return WebhookCreateResponse(
        **resp.model_dump(),
        plaintext_secret=new_secret,
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_webhook(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> Response:
    """Delete a webhook endpoint and delivery history (admin only)."""
    service = WebhookService(db)
    deleted = await service.delete_webhook(id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{id}/test", response_model=WebhookDeliveryResponse)
async def test_webhook(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> WebhookDeliveryResponse:
    """Send a test ping event to verify the webhook endpoint (admin only)."""
    service = WebhookService(db)
    delivery = await service.test_webhook(id)
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found.",
        )
    return WebhookDeliveryResponse.model_validate(delivery)


@router.get("/{id}/deliveries", response_model=WebhookDeliveryListResponse)
async def list_webhook_deliveries(
    id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: WebhookDeliveryStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> WebhookDeliveryListResponse:
    """Get delivery audit history for a webhook (admin and manager)."""
    service = WebhookService(db)
    webhook = await service.get_by_id(id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found.",
        )

    items, total = await service.list_deliveries(
        webhook_id=id, page=page, page_size=page_size, status=status_filter
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return WebhookDeliveryListResponse(
        items=[WebhookDeliveryResponse.model_validate(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
