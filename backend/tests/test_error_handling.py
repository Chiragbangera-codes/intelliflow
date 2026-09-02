"""
Unit and integration tests for Global Error Handling & Request Correlation (Milestone 12).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_request_correlation_id_propagation(async_client: AsyncClient):
    """Verify that incoming X-Request-ID is echoed or generated and attached to response headers."""
    # 1. Custom incoming request ID
    custom_id = "test-req-correlation-123456"
    res = await async_client.get("/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id

    # 2. Auto-generated request ID when omitted
    res_auto = await async_client.get("/health")
    assert res_auto.status_code == 200
    auto_id = res_auto.headers.get("X-Request-ID")
    assert auto_id is not None
    assert len(auto_id) > 10


@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient):
    """Verify defensive HTTP security headers on all responses."""
    res = await async_client.get("/health")
    assert res.status_code == 200
    headers = res.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_standardized_error_envelope_404(async_client: AsyncClient):
    """Verify error envelope for 404 Not Found."""
    res = await async_client.get("/api/v1/nonexistent-route-for-testing")
    assert res.status_code == 404
    body = res.json()

    assert body["success"] is False
    assert "message" in body
    assert "error" in body
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "request_id" in body["error"]
    assert res.headers.get("X-Request-ID") == body["error"]["request_id"]


@pytest.mark.asyncio
async def test_standardized_error_envelope_422(async_client: AsyncClient):
    """Verify error envelope for 422 Validation Error."""
    # Send empty payload to register
    res = await async_client.post("/api/v1/auth/register", json={})
    assert res.status_code == 422
    body = res.json()

    assert body["success"] is False
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in body["error"]
    assert isinstance(body["error"]["details"], list)
