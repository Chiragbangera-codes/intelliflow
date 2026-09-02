"""
Health and readiness response schemas for IntelliFlow AI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response schema for the GET /health and GET /api/v1/health/live endpoints."""

    status: str = "ok"
    app: str = "IntelliFlow AI"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DependencyHealthItem(BaseModel):
    """Health status for an individual subsystem dependency."""

    status: str  # "healthy", "degraded", "unhealthy"
    latency_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthReadyResponse(BaseModel):
    """Readiness response schema verifying critical system dependencies."""

    status: str  # "healthy", "degraded", "unhealthy"
    dependencies: dict[str, DependencyHealthItem]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SystemDiagnosticsData(BaseModel):
    """Detailed diagnostics metrics for authorized system administrators."""

    status: str
    uptime_seconds: float
    memory_usage_mb: float
    dependencies: dict[str, DependencyHealthItem]
    environment: str
    workers_registered: list[str] = Field(default_factory=list)
    faiss_vectors: int = 0
    active_db_pool_connections: int | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthDetailsResponse(BaseModel):
    """Response envelope for admin diagnostics endpoint."""

    success: bool = True
    data: SystemDiagnosticsData
