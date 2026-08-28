"""
Health check endpoint.

GET /health

Purpose:
  - Kubernetes/Docker liveness and readiness probe target.
  - CI/CD pipeline smoke test after deployment.
  - Monitoring system availability check.

Per API_SPECIFICATION §12:
  - Authentication: not required
  - Response: {"status": "ok"}

This route contains no business logic — it intentionally only
confirms the application process is running and can serve requests.
Database and Redis connectivity checks belong in a separate
`/health/ready` endpoint (future milestone).
"""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description=(
        "Returns the operational status of the API. "
        "No authentication required. "
        "Used by load balancers and monitoring systems."
    ),
    operation_id="health_check",
)
async def health_check() -> HealthResponse:
    """Return API health status."""
    return HealthResponse(status="ok")
