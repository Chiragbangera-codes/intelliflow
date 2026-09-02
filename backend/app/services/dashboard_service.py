"""
Dashboard service — aggregate statistics for the authenticated dashboard.

Only metrics answerable from Milestone 1-3 tables are included:
  - total_departments : COUNT from departments (non-deleted)
  - total_employees   : COUNT from employee_profiles (non-deleted)
  - total_documents   : COUNT scoped by role:
                          admin/hr → all active documents
                          others   → only the user's own documents

Revenue, workflow, AI-usage, and notification stats belong to
future milestones (5-10) and must NOT be added here prematurely
(DEVELOPMENT_ROADMAP.md §2: "Build only what the current milestone requires").

Architecture: API → DashboardService → Repositories → PostgreSQL
All counts are single SQL COUNT queries — no N+1.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.employee_profile_repository import EmployeeProfileRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.dashboard import DashboardStatsResponse

logger = logging.getLogger(__name__)

_ADMIN_ROLES = frozenset({"admin", "hr"})


class DashboardService:
    """Computes aggregate dashboard statistics from the database."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the database session and initialise repositories."""
        self._departments = DepartmentRepository(session)
        self._employees = EmployeeProfileRepository(session)
        self._documents = DocumentRepository(session)
        self._workflows = WorkflowRepository(session)

    async def get_stats(self, *, actor: User) -> DashboardStatsResponse:
        """
        Return dashboard KPI counts for the authenticated user.

        Three separate COUNT queries — each is O(1) in PostgreSQL with
        the existing indexes on deleted_at columns.

        Args:
            actor: The authenticated user whose role determines document scope.

        Returns:
            DashboardStatsResponse with current counts.
        """
        total_departments = await self._departments.count_active()
        total_employees = await self._employees.count_active()

        role_name = (
            actor.role.name.lower()
            if actor.role and hasattr(actor.role, "name") and actor.role.name
            else str(getattr(actor, "role", "")).lower()
        )
        if role_name in _ADMIN_ROLES:
            total_documents = await self._documents.count_all_active()
        else:
            total_documents = await self._documents.count_by_owner(actor.id)

        # Milestone 8 — workflow counts (two efficient COUNT queries)
        total_workflows = await self._workflows.count_active_workflows()
        pending_executions = await self._workflows.count_pending_executions()

        logger.debug(
            "Dashboard stats fetched: user=%s depts=%d employees=%d docs=%d "
            "workflows=%d pending_exec=%d",
            actor.id,
            total_departments,
            total_employees,
            total_documents,
            total_workflows,
            pending_executions,
        )

        return DashboardStatsResponse(
            total_departments=total_departments,
            total_employees=total_employees,
            total_documents=total_documents,
            total_workflows=total_workflows,
            pending_executions=pending_executions,
        )
