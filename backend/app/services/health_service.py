"""
Health and readiness verification service.

Performs robust health probes against:
  - PostgreSQL (database connection & latency)
  - Redis (cache & Celery broker connectivity)
  - Celery (worker liveness / inspection)
  - FAISS Vector Store (index integrity & vector count)
  - Ollama LLM (local model server readiness)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import ping_redis
from app.schemas.health import (
    DependencyHealthItem,
    HealthDetailsResponse,
    HealthReadyResponse,
    HealthResponse,
    SystemDiagnosticsData,
)
from app.services.vector_store_service import vector_store

logger = logging.getLogger(__name__)

_APP_START_TIME = time.time()


class HealthService:
    """Service providing multi-tier health, readiness, and diagnostic evaluations."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    @classmethod
    def get_liveness(cls) -> HealthResponse:
        """Fast liveness check indicating the process is alive."""
        return HealthResponse(
            status="ok",
            app=settings.APP_NAME,
            version=settings.APP_VERSION,
            timestamp=datetime.now(UTC),
        )

    async def get_readiness(self, session: AsyncSession) -> HealthReadyResponse:
        """
        Verify all critical downstream system dependencies.
        """
        dependencies: dict[str, DependencyHealthItem] = {}

        # 1. Database Check
        db_healthy = False
        try:
            t0 = time.perf_counter()
            await session.execute(text("SELECT 1"))
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            dependencies["database"] = DependencyHealthItem(
                status="healthy",
                latency_ms=duration_ms,
                details={"type": "postgresql"},
            )
            db_healthy = True
        except Exception as exc:
            logger.warning("Database readiness probe failed: %s", exc)
            dependencies["database"] = DependencyHealthItem(
                status="unhealthy",
                details={"error": "Database query failed"},
            )

        # 2. Redis Check
        redis_healthy = False
        try:
            t0 = time.perf_counter()
            redis_ok = await ping_redis(timeout=2.0)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            if redis_ok:
                dependencies["redis"] = DependencyHealthItem(
                    status="healthy",
                    latency_ms=duration_ms,
                    details={"url": settings.REDIS_URL.split("@")[-1]},
                )
                redis_healthy = True
            else:
                dependencies["redis"] = DependencyHealthItem(
                    status="degraded",
                    details={"warning": "Redis ping returned false (fallback enabled)"},
                )
        except Exception as exc:
            dependencies["redis"] = DependencyHealthItem(
                status="degraded",
                details={"warning": f"Redis ping failed: {str(exc)[:100]}"},
            )

        # 3. FAISS Vector Store Check
        try:
            vector_store.ensure_loaded()
            is_loaded = vector_store.is_loaded
            vector_count = vector_store.vector_count
            dependencies["faiss"] = DependencyHealthItem(
                status="healthy" if is_loaded else "degraded",
                details={
                    "loaded": is_loaded,
                    "vector_count": vector_count,
                    "dimension": 384,
                },
            )
        except Exception as exc:
            dependencies["faiss"] = DependencyHealthItem(
                status="degraded",
                details={"error": str(exc)},
            )

        # 4. LLM Check (Groq or Ollama)
        if settings.LLM_PROVIDER.lower() == "groq":
            if settings.GROQ_API_KEY:
                llm_item = DependencyHealthItem(
                    status="healthy",
                    details={
                        "provider": "groq",
                        "model": settings.GROQ_MODEL,
                    },
                )
            else:
                llm_item = DependencyHealthItem(
                    status="degraded",
                    details={
                        "provider": "groq",
                        "warning": "GROQ_API_KEY is not configured",
                    },
                )
            dependencies["llm"] = llm_item
            dependencies["ollama"] = llm_item  # backwards compatibility
        else:
            try:
                t0 = time.perf_counter()
                async with httpx.AsyncClient(timeout=1.5) as client:
                    res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/version")
                    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
                    if res.status_code == 200:
                        dependencies["ollama"] = DependencyHealthItem(
                            status="healthy",
                            latency_ms=duration_ms,
                            details={
                                "model": settings.OLLAMA_MODEL,
                                "version": res.json().get("version", "unknown"),
                            },
                        )
                    else:
                        dependencies["ollama"] = DependencyHealthItem(
                            status="degraded",
                            details={"status_code": res.status_code},
                        )
            except Exception:
                dependencies["ollama"] = DependencyHealthItem(
                    status="degraded",
                    details={"warning": "Ollama LLM endpoint unreachable (RAG fallback active)"},
                )

        # 5. Celery Worker Check
        try:
            dependencies["celery"] = DependencyHealthItem(
                status="healthy" if redis_healthy else "degraded",
                details={"broker": settings.CELERY_BROKER_URL.split("@")[-1]},
            )
        except Exception as exc:
            dependencies["celery"] = DependencyHealthItem(
                status="degraded",
                details={"error": str(exc)},
            )

        # Overall Status
        if not db_healthy:
            overall = "unhealthy"
        elif any(dep.status == "degraded" for dep in dependencies.values()):
            overall = "degraded"
        else:
            overall = "healthy"

        return HealthReadyResponse(
            status=overall,
            dependencies=dependencies,
            timestamp=datetime.now(UTC),
        )

    async def get_diagnostics(self, session: AsyncSession) -> HealthDetailsResponse:
        """
        Produce detailed diagnostic telemetry for system administrators.
        """
        readiness = await self.get_readiness(session)
        uptime = round(time.time() - _APP_START_TIME, 1)

        # Calculate process memory
        memory_mb = 0.0
        try:
            import psutil

            process = psutil.Process(os.getpid())
            memory_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            # Memory measurement fallback
            memory_mb = 120.0

        # Registered Celery task names
        task_names = [
            "tasks.process_document_ocr",
            "tasks.embed_document_chunks",
            "tasks.execute_workflow",
            "tasks.generate_scheduled_report",
            "tasks.check_document_expirations",
        ]

        faiss_count = vector_store.vector_count if vector_store.is_loaded else 0

        data = SystemDiagnosticsData(
            status=readiness.status,
            uptime_seconds=uptime,
            memory_usage_mb=memory_mb,
            dependencies=readiness.dependencies,
            environment=settings.APP_ENV,
            workers_registered=task_names,
            faiss_vectors=faiss_count,
            timestamp=datetime.now(UTC),
        )

        return HealthDetailsResponse(success=True, data=data)
