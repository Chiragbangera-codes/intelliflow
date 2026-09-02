"""
Request correlation ID and structured request logging middleware.

Responsibilities:
  - Extract incoming `X-Request-ID` or generate a new UUIDv4
  - Store request_id in request.state and contextvars for logging
  - Attach `X-Request-ID` to all HTTP response headers
  - Structured access logging with latency and status code
"""

from __future__ import annotations

import contextvars
import logging
import re
import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.access")

# ContextVar storing current request ID in async task context
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def get_current_request_id() -> str:
    """Return the active correlation request ID for the current async task context."""
    return request_id_ctx.get() or ""


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that manages request correlation IDs and structured access logging.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        raw_header = request.headers.get("X-Request-ID", "").strip()

        # Validate incoming request ID format, otherwise generate fresh UUIDv4
        if raw_header and _SAFE_ID_RE.match(raw_header):
            request_id = raw_header
        else:
            request_id = str(uuid.uuid4())

        # Set on state and contextvar
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            # Attach correlation ID to response headers
            response.headers["X-Request-ID"] = request_id

            # Log structured access info (skip health probe spam unless error)
            if not request.url.path.startswith("/health") or response.status_code >= 400:
                logger.info(
                    "[%s] %s %s -> %s (%sms) [client: %s]",
                    request_id,
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                    client_ip,
                )

            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "[%s] %s %s -> EXCEPTION %s (%sms) [client: %s]",
                request_id,
                request.method,
                request.url.path,
                exc.__class__.__name__,
                duration_ms,
                client_ip,
            )
            raise
        finally:
            request_id_ctx.reset(token)
