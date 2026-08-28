"""
Celery worker async task runner.

Provides run_in_worker(), an execution wrapper that runs an async coroutine
inside a dedicated asyncio event loop while properly disposing of SQLAlchemy's
async engine connection pool before the event loop closes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

from app.core.database import engine

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_in_worker(coro: Coroutine[Any, Any, T]) -> T:
    """
    Execute an async coroutine within a fresh event loop and safely dispose
    of all pooled asyncpg connections before the loop is closed.

    This prevents cross-loop contamination where connections created in one
    event loop (e.g. FAISS warm-up or a previous Celery task) retain futures
    bound to that closed loop, causing:
        RuntimeError: Future attached to a different loop
    on subsequent task executions.
    """

    async def _wrapper() -> T:
        try:
            return await coro
        finally:
            try:
                await engine.dispose()
                logger.debug("run_in_worker: engine pool disposed successfully.")
            except Exception as dispose_exc:  # noqa: BLE001
                logger.warning(
                    "run_in_worker: engine.dispose() failed during teardown: %s",
                    dispose_exc,
                )

    return asyncio.run(_wrapper())
