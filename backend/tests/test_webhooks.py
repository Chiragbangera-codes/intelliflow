"""
Tests for Webhook subsystem: HMAC signing, delivery logging, SSRF enforcement, and API lifecycle.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookDeliveryStatus
from app.services.webhook_service import (
    WebhookService,
    compute_hmac_signature,
    mask_secret,
)


class TestWebhooks:
    """Test webhook functionality, HMAC-SHA256 signatures, and API endpoints."""

    def test_hmac_signature_generation(self) -> None:
        """Verify HMAC-SHA256 signature format."""
        secret = "whsec_test1234567890"
        payload_bytes = json.dumps({"test": "data"}).encode()
        timestamp = 1700000000

        sig = compute_hmac_signature(secret, payload_bytes, timestamp)
        assert "t=" in sig
        assert "v1=" in sig

    def test_secret_masking(self) -> None:
        """Verify secret masking hides most characters."""
        assert mask_secret("whsec_123456789abcdef") == "whsec_...cdef"
        assert mask_secret("short") == "********"

    @pytest.mark.asyncio
    async def test_create_webhook_and_secret_masking(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """Verify POST /api/v1/webhooks generates a secret once and masks it on GET."""
        create_payload = {
            "name": "Audit Logging Hook",
            "url": "https://httpbin.org/post",
            "subscribed_events": ["document.created", "workflow.*"],
            "description": "Enterprise audit webhook endpoint",
        }

        res = await async_client.post(
            "/api/v1/webhooks",
            json=create_payload,
            headers=admin_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Audit Logging Hook"
        assert data["plaintext_secret"] is not None
        assert data["plaintext_secret"].startswith("whsec_")
        assert data["masked_secret"] is not None

        webhook_id = data["id"]

        # GET single webhook — plaintext_secret must be None
        get_res = await async_client.get(
            f"/api/v1/webhooks/{webhook_id}",
            headers=admin_headers,
        )
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data.get("plaintext_secret") is None
        assert get_data["masked_secret"] == data["masked_secret"]

    @pytest.mark.asyncio
    async def test_create_webhook_ssrf_rejection(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """Verify that private IP / loopback URLs are rejected with HTTP 422."""
        create_payload = {
            "name": "Malicious Hook",
            "url": "http://127.0.0.1:8080/internal",
            "subscribed_events": ["*"],
        }

        res = await async_client.post(
            "/api/v1/webhooks",
            json=create_payload,
            headers=admin_headers,
        )
        assert res.status_code in (400, 422)
        assert "SSRF" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_deliver_webhook_mocked_success(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Verify webhook delivery creates delivery records with response status."""
        service = WebhookService(db_session)
        webhook, _ = await service.create_webhook(
            name="Test Mock Hook",
            url="https://httpbin.org/post",
            subscribed_events=["test.event"],
        )

        mock_resp = Response(
            status_code=200,
            json={"success": True},
            request=AsyncMock(),
        )

        with patch("app.utils.ssrf.safe_http_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            delivery = await service.execute_delivery(
                webhook=webhook,
                event_type="test.event",
                payload={"user": "alice"},
            )

            assert delivery.status == WebhookDeliveryStatus.SUCCESS
            assert delivery.response_status_code == 200
            assert delivery.duration_ms is not None

    @pytest.mark.asyncio
    async def test_webhook_delivery_history_api(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        """Verify GET /api/v1/webhooks/{id}/deliveries lists delivery history."""
        service = WebhookService(db_session)
        webhook, _ = await service.create_webhook(
            name="Delivery History Hook",
            url="https://httpbin.org/post",
            subscribed_events=["*"],
        )

        # Mock delivery
        mock_resp = Response(status_code=200, json={"ack": True}, request=AsyncMock())
        with patch("app.utils.ssrf.safe_http_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await service.execute_delivery(
                webhook=webhook,
                event_type="test.ping",
                payload={"ping": "pong"},
            )

        res = await async_client.get(
            f"/api/v1/webhooks/{webhook.id}/deliveries",
            headers=admin_headers,
        )
        assert res.status_code == 200
        deliveries_data = res.json()
        assert deliveries_data["total"] >= 1
        assert deliveries_data["items"][0]["event_type"] == "test.ping"
