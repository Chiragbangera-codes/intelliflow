"""
Rate limiting dependency and middleware for sensitive API routes.

Uses Redis sliding-window counter with in-memory fallback for local testing and resilience.
"""

import logging
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis import SlidingWindowRateLimiter

logger = logging.getLogger(__name__)


def _get_client_identifier(request: Request) -> str:
    """Resolve client IP or authenticated user ID for rate limit key."""
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    return f"ip:{client_ip}"


class RateLimiter:
    """
    FastAPI dependency that enforces sliding-window rate limits per route group.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int = 60,
        group: str = "default",
        key_func: Callable[[Request], str] | None = None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.group = group
        self.key_func = key_func or _get_client_identifier

    async def __call__(self, request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        ident = self.key_func(request)
        rate_key = f"{self.group}:{ident}"

        is_allowed, remaining, retry_after = await SlidingWindowRateLimiter.check_rate_limit(
            key=rate_key,
            max_requests=self.max_requests,
            window_seconds=self.window_seconds,
        )

        request.state.rate_limit_limit = self.max_requests
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_retry_after = retry_after

        if not is_allowed:
            logger.warning(
                "Rate limit exceeded on group '%s' for client '%s'. Retry after %ss.",
                self.group,
                ident,
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please slow down and try again in {retry_after} seconds.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                },
            )
