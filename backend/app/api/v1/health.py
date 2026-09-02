"""
Multi-tier Health and Readiness Check endpoints.

Routes:
  GET /health                — Root liveness probe (backwards-compatible)
  GET /api/v1/health/live    — Liveness probe (process is running)
  GET /api/v1/health/ready   — Readiness probe (PostgreSQL, Redis, Celery, FAISS, Ollama)
  GET /api/v1/health/details — Deep diagnostics for authorized administrators
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.user import User
from app.schemas.health import (
    HealthDetailsResponse,
    HealthReadyResponse,
    HealthResponse,
)
from app.services.health_service import HealthService

router = APIRouter(tags=["Health"])


def _get_health_service() -> HealthService:
    return HealthService()


@router.get(
    "/health",
    summary="Root Liveness Probe",
    description="Returns basic operational status. No authentication required.",
    operation_id="health_check_root",
)
async def health_check_root() -> dict[str, str]:
    """Root liveness probe — returns status ok."""
    return {"status": "ok"}


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Liveness Probe",
    description="Confirms that the application process is running and accepting traffic.",
    operation_id="health_live",
)
async def health_live() -> HealthResponse:
    """Process liveness probe."""
    return HealthService.get_liveness()


@router.get(
    "/health/ready",
    response_model=HealthReadyResponse,
    summary="Readiness Probe",
    description=(
        "Verifies downstream dependencies (PostgreSQL, Redis, Celery, FAISS, Ollama). "
        "Returns HTTP 200 when ready or degraded, HTTP 503 when critical dependencies fail."
    ),
    operation_id="health_ready",
)
async def health_ready(
    response: Response,
    db: AsyncSession = Depends(get_db),
    health_svc: HealthService = Depends(_get_health_service),
) -> HealthReadyResponse:
    """System readiness probe."""
    result = await health_svc.get_readiness(db)
    if result.status == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/health/details",
    response_model=HealthDetailsResponse,
    summary="Deep System Diagnostics (Admin only)",
    description="Provides detailed telemetry on memory, uptime, database pool, and background workers.",
    operation_id="health_details",
)
async def health_details(
    _current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    health_svc: HealthService = Depends(_get_health_service),
) -> HealthDetailsResponse:
    """Detailed system diagnostic metrics."""
    return await health_svc.get_diagnostics(db)
