"""
Redis connection management and resilient sliding-window rate limiting.

Provides:
  - Singleton async Redis client with connection pooling
  - Health check pinging
  - Sliding-window rate limiter with in-memory fallback for testing/offline resilience
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_redis_client: aioredis.Redis | None = None

# In-memory sliding window fallback store: key -> deque of timestamps
_memory_rate_limit_store: dict[str, deque[float]] = defaultdict(deque)


def get_redis_pool() -> ConnectionPool:
    """Initialize or return the singleton async Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            decode_responses=True,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    """Return the singleton async Redis client."""
    global _redis_client
    if _redis_client is None:
        pool = get_redis_pool()
        _redis_client = aioredis.Redis(connection_pool=pool)
    return _redis_client


async def close_redis() -> None:
    """Gracefully close Redis connection pool during shutdown."""
    global _pool, _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as exc:
            logger.warning("Error closing Redis client: %s", exc)
        _redis_client = None

    if _pool is not None:
        try:
            await _pool.disconnect()
        except Exception as exc:
            logger.warning("Error disconnecting Redis pool: %s", exc)
        _pool = None


async def ping_redis(timeout: float = 2.0) -> bool:
    """
    Test connectivity to the Redis server.

    Returns True if Redis is reachable and responds to PING, False otherwise.
    Never raises exceptions.
    """
    try:
        client = get_redis()
        # Test ping with a quick timeout
        res = await client.ping()
        return bool(res)
    except Exception:
        return False


class SlidingWindowRateLimiter:
    """
    Sliding-window rate limiter.

    Uses Redis sorted sets for atomic distributed rate limiting when Redis is available,
    with automatic in-memory sliding-window fallback for offline development/testing.
    """

    @classmethod
    async def check_rate_limit(
        cls,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """
        Check and record a request against a sliding-window rate limit.

        Args:
            key: Unique rate limit bucket key (e.g., 'rate:auth:login:127.0.0.1').
            max_requests: Maximum allowed requests within the time window.
            window_seconds: Window duration in seconds (default 60).

        Returns:
            Tuple of (is_allowed: bool, remaining_requests: int, retry_after_seconds: int).
        """
        now = time.time()
        clear_before = now - window_seconds

        # Try Redis first
        try:
            client = get_redis()
            redis_key = f"rate_limit:{key}"
            now_ms = int(now * 1000)
            clear_before_ms = int(clear_before * 1000)

            # Use Redis pipeline for atomic sliding window evaluation
            pipe = client.pipeline(transaction=True)
            pipe.zremrangebyscore(redis_key, "-inf", clear_before_ms)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(now_ms): now_ms})
            pipe.expire(redis_key, window_seconds + 5)
            results = await pipe.execute()

            current_count = int(results[1])
            if current_count < max_requests:
                remaining = max(0, max_requests - (current_count + 1))
                return True, remaining, 0

            # Limit exceeded — get oldest item to compute retry_after
            oldest = await client.zrange(redis_key, 0, 0, withscores=True)
            retry_after = window_seconds
            if oldest and len(oldest) > 0:
                oldest_ts = oldest[0][1] / 1000.0
                retry_after = max(1, int(oldest_ts + window_seconds - now))

            return False, 0, retry_after

        except Exception as exc:
            # Fallback to in-memory deque if Redis is offline or unreachable
            logger.debug("Redis rate limit fallback to in-memory: %s", exc)
            return cls._check_in_memory(key, max_requests, window_seconds, now, clear_before)

    @classmethod
    def _check_in_memory(
        cls,
        key: str,
        max_requests: int,
        window_seconds: int,
        now: float,
        clear_before: float,
    ) -> tuple[bool, int, int]:
        """In-memory sliding window fallback."""
        bucket = _memory_rate_limit_store[key]

        # Evict timestamps outside the active window
        while bucket and bucket[0] <= clear_before:
            bucket.popleft()

        if len(bucket) < max_requests:
            bucket.append(now)
            remaining = max_requests - len(bucket)
            return True, remaining, 0

        # Exceeded limit
        oldest_ts = bucket[0]
        retry_after = max(1, int(oldest_ts + window_seconds - now))
        return False, 0, retry_after

    @classmethod
    def reset_in_memory(cls) -> None:
        """Clear the in-memory fallback store (useful in test setups)."""
        _memory_rate_limit_store.clear()
