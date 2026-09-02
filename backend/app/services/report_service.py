"""
Report service — business logic for report generation (Phase 9).

Architecture:
  API → ReportService → ReportRepository → PostgreSQL
                      ↘ Celery (fire-and-forget generate_report task)

Flow:
  1. POST /reports → ReportService.request_report()
     - Creates a Report record in PENDING status
     - Enqueues generate_report Celery task
     - Returns immediately with the report ID and status=PENDING

  2. Celery worker → generate_report task
     - Fetches data from AnalyticsRepository
     - Generates CSV/XLSX/PDF file
     - Calls ReportRepository.update_status(COMPLETED, file_path=...)

  3. GET /reports/{id} → ReportService.get_report()
     - Returns current status (PENDING / COMPLETED / FAILED)
     - Includes file_path when COMPLETED

Security:
  - Employees can only view their own reports.
  - Admins, HR, managers, and finance roles can view all reports.
  - File paths are server-internal; files are served from the storage layer.
"""

from __future__ import annotations

import logging
import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report, ReportStatus
from app.models.user import User
from app.repositories.report_repository import ReportRepository
from app.schemas.report_schemas import (
    ReportGenerateRequest,
    ReportListResponse,
    ReportResponse,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Roles that can view all reports (not just their own)
_ADMIN_VIEW_ROLES = frozenset({"admin", "hr", "manager", "finance"})


class ReportService:
    """Business logic for report lifecycle management."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject database session."""
        self._session = session
        self._repo = ReportRepository(session)

    # =========================================================================
    # Request report generation
    # =========================================================================

    async def request_report(
        self,
        request: ReportGenerateRequest,
        *,
        actor: User,
    ) -> ReportResponse:
        """
        Create a Report record and enqueue a Celery generation task.

        Returns immediately with status=PENDING. The Celery task transitions
        the report to COMPLETED or FAILED.

        Args:
            request: Validated request (report_type, format, filters).
            actor:   Authenticated user requesting the report.

        Returns:
            ReportResponse with status=PENDING.
        """
        report = Report(
            report_type=request.report_type,
            format=request.format,
            status=ReportStatus.PENDING,
            generated_by=actor.id,
        )
        saved = await self._repo.create(report)
        await self._session.commit()
        await self._session.refresh(saved)

        # Enqueue the Celery task — fire and forget
        try:
            celery_app.send_task(
                "app.workers.report_tasks.generate_report",
                args=[str(saved.id), request.report_type, request.format, request.filters],
            )
            logger.info(
                "Report enqueued: id=%s type=%s format=%s actor=%s",
                saved.id,
                request.report_type,
                request.format,
                actor.id,
            )
        except Exception as exc:  # noqa: BLE001
            # Task dispatch failure must not fail the API request — the
            # report record is in PENDING.
            logger.error("Failed to enqueue report task for report %s: %s", saved.id, exc)

        return ReportResponse.model_validate(saved)

    # =========================================================================
    # List and retrieve
    # =========================================================================

    async def list_reports(
        self,
        *,
        actor: User,
        page: int = 1,
        page_size: int = 20,
    ) -> ReportListResponse:
        """
        Return paginated reports.

        Admin/HR/manager/finance roles see all reports.
        Employees see only reports they generated.
        """
        page_size = min(max(page_size, 1), 100)
        offset = (page - 1) * page_size

        role_name = (
            actor.role.name.lower()
            if actor.role and hasattr(actor.role, "name") and actor.role.name
            else str(getattr(actor, "role", "")).lower()
        )

        if role_name in _ADMIN_VIEW_ROLES:
            records = await self._repo.list_all(limit=page_size, offset=offset)
            total = await self._repo.count_all()
        else:
            records = await self._repo.list_by_user(actor.id, limit=page_size, offset=offset)
            total = await self._repo.count_by_user(actor.id)

        total_pages = max(1, math.ceil(total / page_size))
        return ReportListResponse(
            data=[ReportResponse.model_validate(r) for r in records],
            meta={
                "page": page,
                "page_size": page_size,
                "total_items": total,
                "total_pages": total_pages,
            },
        )

    async def get_report(
        self,
        report_id: uuid.UUID,
        *,
        actor: User,
    ) -> ReportResponse:
        """
        Return a report by ID, enforcing ownership for non-admin roles.

        Args:
            report_id: UUID of the report.
            actor:     Authenticated user.

        Raises:
            HTTPException 404: Report not found.
            HTTPException 403: User does not own the report.
        """
        record = await self._repo.get_by_id(report_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found.",
            )

        # Ownership check for non-privileged roles
        role_name = (
            actor.role.name.lower()
            if actor.role and hasattr(actor.role, "name") and actor.role.name
            else str(getattr(actor, "role", "")).lower()
        )
        if role_name not in _ADMIN_VIEW_ROLES:
            if record.generated_by != actor.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to view this report.",
                )

        return ReportResponse.model_validate(record)

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _mark_failed(
        self,
        report_id: uuid.UUID,
        reason: str,
    ) -> None:
        """Synchronously mark a report as FAILED (used when Celery is unavailable)."""
        try:
            # We need a fresh session context here since we already committed above.
            await self._repo.update_status(
                report_id,
                status=ReportStatus.FAILED,
            )
            await self._session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to mark report %s as FAILED: %s", report_id, exc)
