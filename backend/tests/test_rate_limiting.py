"""
Unit and integration tests for Rate Limiting (Milestone 12).
"""

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.redis import SlidingWindowRateLimiter


@pytest.fixture(autouse=True)
def enable_rate_limiting():
    prev = settings.RATE_LIMIT_ENABLED
    settings.RATE_LIMIT_ENABLED = True
    SlidingWindowRateLimiter.reset_in_memory()
    yield
    settings.RATE_LIMIT_ENABLED = prev
    SlidingWindowRateLimiter.reset_in_memory()


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_memory():
    """Verify in-memory sliding window rate limit counter."""
    SlidingWindowRateLimiter.reset_in_memory()
    key = "test:ip:10.0.0.1"

    # Allow 3 requests per 10s
    for i in range(3):
        allowed, rem, retry = await SlidingWindowRateLimiter.check_rate_limit(
            key, max_requests=3, window_seconds=10
        )
        assert allowed is True
        assert rem == 2 - i

    # 4th request must be rejected
    allowed, rem, retry = await SlidingWindowRateLimiter.check_rate_limit(
        key, max_requests=3, window_seconds=10
    )
    assert allowed is False
    assert rem == 0
    assert retry > 0

    SlidingWindowRateLimiter.reset_in_memory()


@pytest.mark.asyncio
async def test_auth_login_rate_limiting(async_client: AsyncClient):
    """Verify that hammering /api/v1/auth/login hits 429 Too Many Requests."""
    SlidingWindowRateLimiter.reset_in_memory()

    # Hit /api/v1/auth/login up to limit (5 per min)
    for _ in range(settings.RATE_LIMIT_AUTH_LOGIN):
        res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "WrongPassword123!"},
        )
        assert res.status_code == 401

    # Next attempt should be rate limited (429)
    blocked_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "WrongPassword123!"},
    )
    assert blocked_res.status_code == 429
    assert "Retry-After" in blocked_res.headers
    assert "rate limit" in blocked_res.text.lower() or "too many" in blocked_res.text.lower()

    SlidingWindowRateLimiter.reset_in_memory()
