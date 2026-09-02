"""
Webhook Service.

Provides webhook lifecycle management, HMAC-SHA256 payload signing,
SSRF-shielded delivery execution, and delivery logging.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.webhook import Webhook, WebhookDelivery, WebhookDeliveryStatus
from app.repositories.webhook_repository import WebhookRepository
from app.utils.ssrf import SSRFValidationError, safe_http_post, validate_webhook_url

logger = logging.getLogger(__name__)


def generate_webhook_secret() -> str:
    """Generate a high-entropy secret token for HMAC signing."""
    return f"whsec_{secrets.token_urlsafe(32)}"


def mask_secret(secret: str | None) -> str:
    """Mask a secret string for safe API display."""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "********"
    return f"{secret[:6]}...{secret[-4:]}"


def compute_hmac_signature(secret: str, payload_bytes: bytes, timestamp: int) -> str:
    """
    Compute an HMAC-SHA256 signature over timestamp.payload_bytes.

    Format: sha256=<hex_digest>
    """
    signature_base = f"{timestamp}.".encode() + payload_bytes
    digest = hmac.new(
        secret.encode("utf-8"),
        msg=signature_base,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


class WebhookService:
    """Service for managing and delivering webhooks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WebhookRepository(session)

    async def create_webhook(
        self,
        name: str,
        url: str,
        subscribed_events: list[str],
        description: str | None = None,
        secret: str | None = None,
        is_active: bool = True,
        created_by: uuid.UUID | None = None,
        allow_test_local: bool = False,
    ) -> tuple[Webhook, str]:
        """
        Create a new webhook endpoint.

        Returns:
            tuple of (Webhook, plaintext_secret_once)
        """
        # Validate URL against SSRF
        clean_url = validate_webhook_url(url, allow_test_local=allow_test_local)
        plain_secret = secret.strip() if secret else generate_webhook_secret()

        webhook = await self.repo.create_webhook(
            name=name.strip(),
            url=clean_url,
            secret=plain_secret,
            subscribed_events=subscribed_events or ["*"],
            description=description.strip() if description else None,
            is_active=is_active,
            created_by=created_by,
        )
        await self.session.commit()
        return webhook, plain_secret

    async def get_by_id(self, webhook_id: uuid.UUID) -> Webhook | None:
        """Fetch a webhook by ID."""
        return await self.repo.get_by_id(webhook_id)

    async def list_webhooks(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
    ) -> tuple[list[Webhook], int]:
        """List webhooks with pagination."""
        return await self.repo.list_webhooks(page=page, page_size=page_size, is_active=is_active)

    async def update_webhook(
        self,
        webhook_id: uuid.UUID,
        name: str | None = None,
        url: str | None = None,
        subscribed_events: list[str] | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        rotate_secret: bool = False,
        allow_test_local: bool = False,
    ) -> tuple[Webhook | None, str | None]:
        """
        Update a webhook and optionally rotate its secret.

        Returns:
            tuple of (Webhook, new_plaintext_secret_if_rotated)
        """
        clean_url = None
        if url is not None:
            clean_url = validate_webhook_url(url, allow_test_local=allow_test_local)

        new_secret = generate_webhook_secret() if rotate_secret else None

        updated = await self.repo.update_webhook(
            webhook_id=webhook_id,
            name=name.strip() if name else None,
            url=clean_url,
            secret=new_secret,
            subscribed_events=subscribed_events,
            description=description.strip() if description is not None else None,
            is_active=is_active,
        )
        if updated:
            await self.session.commit()
        return updated, new_secret

    async def delete_webhook(self, webhook_id: uuid.UUID) -> bool:
        """Delete a webhook and cascade deliveries."""
        deleted = await self.repo.delete_webhook(webhook_id)
        if deleted:
            await self.session.commit()
        return deleted

    async def execute_delivery(
        self,
        webhook: Webhook,
        event_type: str,
        payload: dict[str, Any],
        event_id: uuid.UUID | None = None,
        correlation_id: str | None = None,
        allow_test_local: bool = False,
    ) -> WebhookDelivery:
        """
        Sign and dispatch a webhook payload with SSRF protection and delivery logging.
        """
        timestamp = int(time.time())
        corr_id = correlation_id or str(uuid.uuid4())
        ev_id_str = str(event_id) if event_id else str(uuid.uuid4())

        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = compute_hmac_signature(webhook.secret, payload_bytes, timestamp)

        request_headers = {
            "Content-Type": "application/json",
            "User-Agent": f"IntelliFlow-Webhook/{settings.APP_VERSION}",
            "X-IntelliFlow-Event": event_type,
            "X-IntelliFlow-Event-Id": ev_id_str,
            "X-IntelliFlow-Timestamp": str(timestamp),
            "X-IntelliFlow-Signature": signature,
            "X-IntelliFlow-Correlation-Id": corr_id,
        }

        start_time = time.monotonic()
        status_code = None
        response_body = None
        response_headers = None
        error_msg = None
        delivery_status = WebhookDeliveryStatus.PENDING

        try:
            status_code, response_body, response_headers = await safe_http_post(
                url=webhook.url,
                headers=request_headers,
                content=payload_bytes,
                timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS,
                allow_test_local=allow_test_local,
            )
            duration_ms = int((time.monotonic() - start_time) * 1000)

            if 200 <= status_code < 300:
                delivery_status = WebhookDeliveryStatus.SUCCESS
            else:
                delivery_status = WebhookDeliveryStatus.FAILED
                error_msg = f"HTTP {status_code} returned by webhook receiver."

        except SSRFValidationError as ssrf_err:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            delivery_status = WebhookDeliveryStatus.FAILED
            error_msg = f"SSRF Protection Violation: {ssrf_err}"
            logger.warning(
                "SSRF blocked for webhook %s (%s): %s", webhook.id, webhook.url, ssrf_err
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            delivery_status = WebhookDeliveryStatus.FAILED
            error_msg = f"Network or Dispatch Error: {exc}"
            logger.warning("Webhook delivery error for %s: %s", webhook.id, exc)

        # Record delivery log
        delivery = await self.repo.create_delivery(
            webhook_id=webhook.id,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            request_headers=request_headers,
            response_status_code=status_code,
            response_body=response_body[:2000] if response_body else None,
            response_headers=response_headers,
            duration_ms=duration_ms,
            status=delivery_status,
            error_message=error_msg,
        )

        if delivery_status == WebhookDeliveryStatus.SUCCESS:
            await self.repo.update_last_delivery_at(webhook.id, datetime.now(UTC))

        await self.session.commit()
        return delivery

    async def test_webhook(
        self, webhook_id: uuid.UUID, allow_test_local: bool = False
    ) -> WebhookDelivery | None:
        """Send a test ping event to the webhook."""
        webhook = await self.get_by_id(webhook_id)
        if not webhook:
            return None

        test_payload = {
            "test": True,
            "message": "IntelliFlow Webhook Connectivity Verification Ping",
            "webhook_id": str(webhook.id),
            "webhook_name": webhook.name,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self.execute_delivery(
            webhook=webhook,
            event_type="webhook.test",
            payload=test_payload,
            allow_test_local=allow_test_local,
        )

    async def list_deliveries(
        self,
        webhook_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        status: WebhookDeliveryStatus | None = None,
    ) -> tuple[list[WebhookDelivery], int]:
        """Query delivery logs."""
        return await self.repo.list_deliveries(
            webhook_id=webhook_id,
            page=page,
            page_size=page_size,
            status=status,
        )
