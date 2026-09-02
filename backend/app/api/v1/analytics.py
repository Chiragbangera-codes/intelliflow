"""
Analytics API routes — Phase 9.

Endpoints:
  GET  /api/v1/analytics/kpi          — Overall KPI summary
  GET  /api/v1/analytics/revenue      — Monthly revenue/expense trend
  GET  /api/v1/analytics/departments  — Per-department analytics
  GET  /api/v1/analytics/employees    — Employee headcount + role distribution
  GET  /api/v1/analytics/documents    — Document upload trends + status breakdown
  GET  /api/v1/analytics/workflows    — Workflow execution statistics
  GET  /api/v1/analytics/ai           — AI conversation usage stats

Access:
  All endpoints require authentication (JWT).
  All endpoints require admin, manager, hr, or finance role.
  Route handlers are thin: authenticate → delegate → respond.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.user import User
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Roles allowed to view analytics
_ANALYTICS_ROLES = ("admin", "manager", "hr", "finance")


def _get_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    """Provide an AnalyticsService with the injected DB session."""
    return AnalyticsService(db)


# ---------------------------------------------------------------------------
# KPI Summary
# ---------------------------------------------------------------------------


@router.get(
    "/kpi",
    status_code=status.HTTP_200_OK,
    summary="Overall KPI summary",
    description="Returns aggregated top-level KPIs: headcounts, document totals, "
    "AI conversations, workflow stats, and report counts. "
    "Requires admin, manager, hr, or finance role.",
    responses={
        200: {"description": "KPI data retrieved."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def get_kpi_summary(
    current_user: User = Depends(require_role(*_ANALYTICS_ROLES)),
    svc: AnalyticsService = Depends(_get_service),
) -> dict[str, Any]:
    """Return aggregated KPI metrics."""
    data = await svc.get_kpi_summary()
    return {
        "success": True,
        "message": "KPI summary retrieved successfully.",
        "data": data.model_dump(),
    }


# ---------------------------------------------------------------------------
# Revenue Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/revenue",
    status_code=status.HTTP_200_OK,
    summary="Monthly revenue trend",
    description="Returns 12-month revenue/expense projection for the given year. "
    "Revenue is estimated as salary × multiplier. "
    "Requires admin, manager, hr, or finance role.",
    responses={
        200: {"description": "Revenue data retrieved."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def get_revenue_analytics(
    year: int = Query(
        default=None,
        ge=2000,
        le=2100,
        description="Year to return data for. Defaults to current year.",
    ),
    current_user: User = Depends(require_role(*_ANALYTICS_ROLES)),
    svc: AnalyticsService = Depends(_get_service),
) -> dict[str, Any]:
    """Return monthly revenue and expense trends."""
    if year is None:
        year = datetime.now().year
    data = await svc.get_revenue_analytics(year)
    return {
        "success": True,
        "message": "Revenue analytics retrieved successfully.",
        "data": data.model_dump(),
    }


# ---------------------------------------------------------------------------
# Department Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/departments",
    status_code=status.HTTP_200_OK,
    summary="Department analytics",
    description="Returns per-department employee counts, average salary, "
    "document count, and active workflow count. "
    "Requires admin, manager, hr, or finance role.",
    responses={
        200: {"description": "Department data retrieved."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def get_department_analytics(
    current_user: User = Depends(require_role(*_ANALYTICS_ROLES)),
    svc: AnalyticsService = Depends(_get_service),
) -> dict[str, Any]:
    """Return per-department analytics breakdown."""
    data = await svc.get_department_analytics()
    return {
        "success": True,
        "message": "Department analytics retrieved successfully.",
        "data": data.model_dump(),
    }


# ---------------------------------------------------------------------------
# Employee Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/employees",
    status_code=status.HTTP_200_OK,
    summary="Employee analytics",
    description="Returns total/active/new employee counts, role distribution, "
    "and monthly headcount trend. "
    "Requires admin, manager, hr, or finance role.",
    responses={
        200: {"description": "Employee analytics retrieved."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def get_employee_analytics(
    current_user: User = Depends(require_role(*_ANALYTICS_ROLES)),
    svc: AnalyticsService = Depends(_get_service),
) -> dict[str, Any]:
    """Return employee headcount and composition analytics."""
    data = await svc.get_employee_analytics()
    return {
        "success": True,
        "message": "Employee analytics retrieved successfully.",
        "data": data.model_dump(),
    }


# ---------------------------------------------------------------------------
# Document Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/documents",
    status_code=status.HTTP_200_OK,
    summary="Document analytics",
    description="Returns document upload trends, status distribution, and "
    "OCR status breakdown. "
    "Requires admin, manager, hr, or finance role.",
    responses={
        200: {"description": "Document analytics retrieved."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def get_document_analytics(
    current_user: User = Depends(require_role(*_ANALYTICS_ROLES)),
    svc: AnalyticsService = Depends(_get_service),
) -> dict[str, Any]:
    """Return document upload trends and status breakdown."""
    data = await svc.get_document_analytics()
    return {
        "success": True,
        "message": "Document analytics retrieved successfully.",
        "data": data.model_dump(),
    }


# ---------------------------------------------------------------------------
# Workflow Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/workflows",
    status_code=status.HTTP_200_OK,
    summary="Workflow analytics",
    description="Returns total executions, status distribution, average duration, "
    "and step-action frequency. "
    "Requires admin, manager, hr, or finance role.",
    responses={
        200: {"description": "Workflow analytics retrieved."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def get_workflow_analytics(
    current_user: User = Depends(require_role(*_ANALYTICS_ROLES)),
    svc: AnalyticsService = Depends(_get_service),
) -> dict[str, Any]:
    """Return workflow execution analytics."""
    data = await svc.get_workflow_analytics()
    return {
        "success": True,
        "message": "Workflow analytics retrieved successfully.",
        "data": data.model_dump(),
    }


# ---------------------------------------------------------------------------
# AI Usage Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/ai",
    status_code=status.HTTP_200_OK,
    summary="AI usage analytics",
    description="Returns total AI conversations, monthly trends, average response "
    "time, and token consumption statistics. "
    "Requires admin, manager, hr, or finance role.",
    responses={
        200: {"description": "AI usage analytics retrieved."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def get_ai_usage_analytics(
    current_user: User = Depends(require_role(*_ANALYTICS_ROLES)),
    svc: AnalyticsService = Depends(_get_service),
) -> dict[str, Any]:
    """Return AI conversation usage analytics."""
    data = await svc.get_ai_usage_analytics()
    return {
        "success": True,
        "message": "AI usage analytics retrieved successfully.",
        "data": data.model_dump(),
    }
