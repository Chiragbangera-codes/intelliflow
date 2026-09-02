"""
Reports API routes — Phase 9.

Endpoints:
  POST /api/v1/reports          — Request async report generation
  GET  /api/v1/reports          — List reports (own or all depending on role)
  GET  /api/v1/reports/{id}     — Get report status / metadata

Flow:
  POST creates a Report record in PENDING status and enqueues a Celery task.
  Clients poll GET /reports/{id} until status transitions to COMPLETED or FAILED.

Access:
  POST: any authenticated user (generates reports scoped to their data)
  GET list: admin/hr/manager/finance see all; employee sees own only
  GET by ID: same ownership rules as list

Route handlers are thin: validate → delegate → respond.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.middleware.rate_limit import RateLimiter
from app.models.user import User
from app.schemas.report_schemas import ReportGenerateRequest
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


def _get_service(db: AsyncSession = Depends(get_db)) -> ReportService:
    """Provide a ReportService with the injected DB session."""
    return ReportService(db)


# ---------------------------------------------------------------------------
# Request report generation
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(
            RateLimiter(
                max_requests=settings.RATE_LIMIT_REPORTS,
                window_seconds=60,
                group="reports_generate",
            )
        )
    ],
    summary="Request report generation",
    description=(
        "Creates a Report record in PENDING status and enqueues an async "
        "Celery task to generate the file. Returns immediately with the "
        "report ID for polling. All authenticated users may request reports."
    ),
    responses={
        202: {"description": "Report generation enqueued."},
        401: {"description": "Not authenticated."},
        422: {"description": "Validation error."},
    },
)
async def request_report(
    data: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
) -> dict[str, Any]:
    """Enqueue async report generation and return the pending record."""
    report = await svc.request_report(data, actor=current_user)
    return {
        "success": True,
        "message": "Report generation enqueued. Poll GET /reports/{id} for status.",
        "data": report.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# List reports
# ---------------------------------------------------------------------------


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List reports",
    description=(
        "Returns a paginated list of reports. "
        "Admin, manager, hr, and finance roles see all reports. "
        "Employees see only their own reports."
    ),
    responses={
        200: {"description": "Reports retrieved successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def list_reports(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page."),
    current_user: User = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
) -> dict[str, Any]:
    """List reports with pagination. Visibility scoped by role."""
    result = await svc.list_reports(actor=current_user, page=page, page_size=page_size)
    return {
        "success": True,
        "message": "Reports retrieved successfully.",
        "data": [r.model_dump(mode="json") for r in result.data],
        "meta": result.meta,
    }


# ---------------------------------------------------------------------------
# Get single report
# ---------------------------------------------------------------------------


@router.get(
    "/{report_id}",
    status_code=status.HTTP_200_OK,
    summary="Get report status",
    description=(
        "Returns current status and metadata for a report. "
        "Used for polling after POST /reports. "
        "Employees can only view their own reports."
    ),
    responses={
        200: {"description": "Report retrieved successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "You do not own this report."},
        404: {"description": "Report not found."},
    },
)
async def get_report(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: ReportService = Depends(_get_service),
) -> dict[str, Any]:
    """Return report status and metadata."""
    report = await svc.get_report(report_id, actor=current_user)
    return {
        "success": True,
        "message": "Report retrieved successfully.",
        "data": report.model_dump(mode="json"),
    }
