"""
Analytics repository — database access layer for Phase 9 analytics queries.

All raw aggregate queries live here. No business logic.

Architecture:
  AnalyticsService → AnalyticsRepository → PostgreSQL
  Never accessed directly from API routes.

Performance notes:
  - All queries use COUNT / SUM / AVG aggregate functions — no full scans.
  - Monthly groupings use date_trunc('month', ...) which is index-friendly.
  - Results are capped at 12 months (current year) to bound memory usage.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Float, Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation import AIConversation
from app.models.department import Department
from app.models.document import Document
from app.models.employee_profile import EmployeeProfile
from app.models.prediction import Prediction
from app.models.report import Report, ReportStatus
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_execution import ExecutionStatus, WorkflowExecution
from app.models.workflow_step import WorkflowStep


class AnalyticsRepository:
    """Handles all aggregate database queries for analytics endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    # =========================================================================
    # KPI Summary
    # =========================================================================

    async def get_kpi_summary(self) -> dict[str, int]:
        """
        Return a dict of aggregated top-level KPIs.

        All values are COUNTs from existing tables — O(1) with indexes.
        """
        total_employees = (
            await self._session.scalar(
                select(func.count())
                .select_from(EmployeeProfile)
                .where(EmployeeProfile.deleted_at.is_(None))
            )
            or 0
        )

        total_documents = (
            await self._session.scalar(
                select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
            )
            or 0
        )

        active_workflows = (
            await self._session.scalar(
                select(func.count())
                .select_from(Workflow)
                .where(
                    Workflow.deleted_at.is_(None),
                    Workflow.is_active.is_(True),
                )
            )
            or 0
        )

        total_ai_conversations = (
            await self._session.scalar(select(func.count()).select_from(AIConversation)) or 0
        )

        completed_executions = (
            await self._session.scalar(
                select(func.count())
                .select_from(WorkflowExecution)
                .where(WorkflowExecution.status == ExecutionStatus.COMPLETED)
            )
            or 0
        )

        total_predictions = (
            await self._session.scalar(select(func.count()).select_from(Prediction)) or 0
        )

        total_reports = (
            await self._session.scalar(
                select(func.count())
                .select_from(Report)
                .where(Report.status == ReportStatus.COMPLETED)
            )
            or 0
        )

        return {
            "total_employees": total_employees,
            "total_documents": total_documents,
            "active_workflows": active_workflows,
            "total_ai_conversations": total_ai_conversations,
            "completed_workflow_executions": completed_executions,
            "total_predictions_run": total_predictions,
            "total_reports_generated": total_reports,
        }

    # =========================================================================
    # Revenue Analytics (salary-based proxy)
    # =========================================================================

    async def get_monthly_salary_totals(self, year: int) -> list[dict[str, object]]:
        """
        Return per-month total salary expenditure for the given year.

        Uses employee_profiles.salary as a proxy for monthly expenses.
        Groups by integer month (1–12).

        Returns list of {'month': int, 'total_salary': float}.
        """
        result = await self._session.execute(
            select(
                func.extract("month", EmployeeProfile.created_at).label("month"),
                func.coalesce(func.sum(cast(EmployeeProfile.salary, Float)), 0.0).label(
                    "total_salary"
                ),
            )
            .where(
                EmployeeProfile.deleted_at.is_(None),
                func.extract("year", EmployeeProfile.created_at) <= year,
            )
            .group_by(func.extract("month", EmployeeProfile.created_at))
            .order_by(func.extract("month", EmployeeProfile.created_at))
        )
        rows = result.all()
        return [{"month": int(r.month), "total_salary": float(r.total_salary)} for r in rows]

    async def get_total_salary(self) -> float:
        """Return sum of all active employee salaries."""
        result = await self._session.scalar(
            select(func.coalesce(func.sum(cast(EmployeeProfile.salary, Float)), 0.0)).where(
                EmployeeProfile.deleted_at.is_(None)
            )
        )
        return float(result or 0.0)

    # =========================================================================
    # Department Analytics
    # =========================================================================

    async def get_department_breakdown(self) -> list[dict[str, object]]:
        """
        Return per-department employee count, average salary, and document count.

        Uses LEFT JOIN to include departments with 0 employees.
        """
        dept_stmt = (
            select(
                Department.id.label("department_id"),
                Department.name.label("department_name"),
                func.count(EmployeeProfile.id).label("employee_count"),
                func.coalesce(func.avg(cast(EmployeeProfile.salary, Float)), 0.0).label(
                    "avg_salary"
                ),
            )
            .outerjoin(
                User,
                (User.department_id == Department.id) & User.deleted_at.is_(None),
            )
            .outerjoin(
                EmployeeProfile,
                (EmployeeProfile.user_id == User.id) & EmployeeProfile.deleted_at.is_(None),
            )
            .where(Department.deleted_at.is_(None))
            .group_by(Department.id, Department.name)
            .order_by(Department.name)
        )
        result = await self._session.execute(dept_stmt)
        rows = result.all()
        return [
            {
                "department_id": r.department_id,
                "department_name": r.department_name,
                "employee_count": r.employee_count,
                "avg_salary": float(r.avg_salary),
            }
            for r in rows
        ]

    async def get_document_count_by_owner_department(self) -> dict[str, int]:
        """Return {department_id_str: doc_count} for documents owned by dept users."""
        result = await self._session.execute(
            select(
                User.department_id.label("dept_id"),
                func.count(Document.id).label("doc_count"),
            )
            .join(Document, Document.owner_id == User.id)
            .where(
                Document.deleted_at.is_(None),
                User.deleted_at.is_(None),
                User.department_id.isnot(None),
            )
            .group_by(User.department_id)
        )
        return {str(r.dept_id): r.doc_count for r in result.all()}

    async def get_active_workflow_count_by_creator_department(self) -> dict[str, int]:
        """Return {department_id_str: active_workflow_count} by creator's department."""
        result = await self._session.execute(
            select(
                User.department_id.label("dept_id"),
                func.count(Workflow.id).label("wf_count"),
            )
            .join(Workflow, Workflow.created_by == User.id)
            .where(
                Workflow.deleted_at.is_(None),
                Workflow.is_active.is_(True),
                User.deleted_at.is_(None),
                User.department_id.isnot(None),
            )
            .group_by(User.department_id)
        )
        return {str(r.dept_id): r.wf_count for r in result.all()}

    # =========================================================================
    # Employee Analytics
    # =========================================================================

    async def get_employee_counts(self) -> dict[str, int]:
        """Return total, active (joined ≤ today), and new-this-month counts."""
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total = (
            await self._session.scalar(
                select(func.count())
                .select_from(EmployeeProfile)
                .where(EmployeeProfile.deleted_at.is_(None))
            )
            or 0
        )

        new_this_month = (
            await self._session.scalar(
                select(func.count())
                .select_from(EmployeeProfile)
                .where(
                    EmployeeProfile.deleted_at.is_(None),
                    EmployeeProfile.created_at >= month_start,
                )
            )
            or 0
        )

        return {
            "total": total,
            "active": total,  # EmployeeProfile has no separate active flag
            "new_this_month": new_this_month,
        }

    async def get_role_distribution(self) -> list[dict[str, object]]:
        """Return count of non-deleted users per role."""
        from app.models.role import Role  # local to avoid circular

        result = await self._session.execute(
            select(
                Role.name.label("role"),
                func.count(User.id).label("count"),
            )
            .join(User, User.role_id == Role.id)
            .where(User.deleted_at.is_(None))
            .group_by(Role.name)
            .order_by(Role.name)
        )
        return [{"role": r.role, "count": r.count} for r in result.all()]

    async def get_monthly_employee_headcount(self, months: int = 12) -> list[dict[str, object]]:
        """
        Return monthly employee profile creation count for the last N months.

        Each row: {'month': 'Jan', 'count': int}
        """
        result = await self._session.execute(
            select(
                func.extract("month", EmployeeProfile.created_at).label("m"),
                func.extract("year", EmployeeProfile.created_at).label("y"),
                func.count(EmployeeProfile.id).label("count"),
            )
            .where(EmployeeProfile.deleted_at.is_(None))
            .group_by("y", "m")
            .order_by("y", "m")
            .limit(months)
        )
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        return [{"month": month_names[int(r.m) - 1], "count": r.count} for r in result.all()]

    # =========================================================================
    # Document Analytics
    # =========================================================================

    async def get_document_status_breakdown(self) -> list[dict[str, object]]:
        """Return {status: count} for all non-deleted documents."""

        result = await self._session.execute(
            select(
                Document.status.label("status"),
                func.count(Document.id).label("count"),
            )
            .where(Document.deleted_at.is_(None))
            .group_by(Document.status)
        )
        return [
            {
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "count": r.count,
            }
            for r in result.all()
        ]

    async def get_document_ocr_status_breakdown(self) -> list[dict[str, object]]:
        """Return {ocr_status: count} for all non-deleted documents."""
        result = await self._session.execute(
            select(
                Document.ocr_status.label("status"),
                func.count(Document.id).label("count"),
            )
            .where(Document.deleted_at.is_(None))
            .group_by(Document.ocr_status)
        )
        return [
            {
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "count": r.count,
            }
            for r in result.all()
        ]

    async def get_monthly_document_uploads(self, months: int = 12) -> list[dict[str, object]]:
        """Return monthly document upload counts (last N months)."""
        result = await self._session.execute(
            select(
                func.extract("month", Document.created_at).label("m"),
                func.extract("year", Document.created_at).label("y"),
                func.count(Document.id).label("count"),
            )
            .where(Document.deleted_at.is_(None))
            .group_by("y", "m")
            .order_by("y", "m")
            .limit(months)
        )
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        return [{"month": month_names[int(r.m) - 1], "count": r.count} for r in result.all()]

    async def get_total_document_count(self) -> int:
        """Return total non-deleted document count."""
        return (
            await self._session.scalar(
                select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
            )
            or 0
        )

    # =========================================================================
    # Workflow Analytics
    # =========================================================================

    async def get_execution_status_breakdown(self) -> list[dict[str, object]]:
        """Return {status: count} for all workflow executions."""
        result = await self._session.execute(
            select(
                WorkflowExecution.status.label("status"),
                func.count(WorkflowExecution.id).label("count"),
            ).group_by(WorkflowExecution.status)
        )
        return [
            {
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "count": r.count,
            }
            for r in result.all()
        ]

    async def get_avg_execution_duration(self) -> float:
        """Return average execution duration (seconds) for completed executions."""
        result = await self._session.scalar(
            select(func.avg(WorkflowExecution.duration)).where(
                WorkflowExecution.status == ExecutionStatus.COMPLETED,
                WorkflowExecution.duration.isnot(None),
            )
        )
        return float(result or 0.0)

    async def get_total_execution_count(self) -> int:
        """Return total workflow execution count."""
        return await self._session.scalar(select(func.count()).select_from(WorkflowExecution)) or 0

    async def get_step_action_frequency(self) -> list[dict[str, object]]:
        """Return {action: count} across all workflow steps."""
        result = await self._session.execute(
            select(
                WorkflowStep.action.label("action"),
                func.count(WorkflowStep.id).label("count"),
            )
            .group_by(WorkflowStep.action)
            .order_by(func.count(WorkflowStep.id).desc())
        )
        return [
            {
                "status": r.action.value if hasattr(r.action, "value") else str(r.action),
                "count": r.count,
            }
            for r in result.all()
        ]

    # =========================================================================
    # AI Usage Analytics
    # =========================================================================

    async def get_ai_usage_stats(self) -> dict[str, object]:
        """Return total conversations, avg response time, and token totals."""
        from sqlalchemy import Integer as SAInt  # avoid shadowing

        total = await self._session.scalar(select(func.count()).select_from(AIConversation)) or 0

        avg_rt = await self._session.scalar(
            select(func.avg(AIConversation.response_time)).where(
                AIConversation.response_time.isnot(None)
            )
        )

        total_prompt = (
            await self._session.scalar(
                select(func.coalesce(func.sum(cast(AIConversation.prompt_tokens, SAInt)), 0))
            )
            or 0
        )

        total_completion = (
            await self._session.scalar(
                select(func.coalesce(func.sum(cast(AIConversation.completion_tokens, SAInt)), 0))
            )
            or 0
        )

        return {
            "total_conversations": total,
            "avg_response_time_seconds": float(avg_rt or 0.0),
            "total_prompt_tokens": int(total_prompt),
            "total_completion_tokens": int(total_completion),
        }

    async def get_monthly_ai_conversations(self, months: int = 12) -> list[dict[str, object]]:
        """Return monthly AI conversation counts."""
        result = await self._session.execute(
            select(
                func.extract("month", AIConversation.created_at).label("m"),
                func.extract("year", AIConversation.created_at).label("y"),
                func.count(AIConversation.id).label("count"),
            )
            .group_by("y", "m")
            .order_by("y", "m")
            .limit(months)
        )
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        return [{"month": month_names[int(r.m) - 1], "count": r.count} for r in result.all()]

    # =========================================================================
    # Data for report generation (used by Celery task)
    # =========================================================================

    async def get_all_employees_for_report(self) -> list[dict[str, object]]:
        """Return flat employee rows for CSV/XLSX export."""
        result = await self._session.execute(
            select(
                User.email,
                User.first_name,
                User.last_name,
                EmployeeProfile.employee_code,
                EmployeeProfile.designation,
                EmployeeProfile.salary,
                EmployeeProfile.date_of_joining,
                EmployeeProfile.created_at,
            )
            .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
            .where(
                EmployeeProfile.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
            .order_by(User.last_name, User.first_name)
        )
        return [
            {
                "email": r.email,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "employee_code": r.employee_code or "",
                "designation": r.designation or "",
                "salary": float(r.salary) if r.salary else 0.0,
                "date_of_joining": str(r.date_of_joining) if r.date_of_joining else "",
                "created_at": str(r.created_at),
            }
            for r in result.all()
        ]

    async def get_all_documents_for_report(self) -> list[dict[str, object]]:
        """Return flat document rows for CSV/XLSX export."""
        result = await self._session.execute(
            select(
                Document.file_name,
                Document.file_type,
                Document.file_size,
                Document.status,
                Document.ocr_status,
                Document.created_at,
                User.email.label("owner_email"),
            )
            .join(User, User.id == Document.owner_id)
            .where(Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
        )
        return [
            {
                "file_name": r.file_name,
                "file_type": r.file_type or "",
                "file_size": r.file_size or 0,
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "ocr_status": r.ocr_status.value
                if hasattr(r.ocr_status, "value")
                else str(r.ocr_status),
                "owner_email": r.owner_email,
                "created_at": str(r.created_at),
            }
            for r in result.all()
        ]

    async def get_all_workflows_for_report(self) -> list[dict[str, object]]:
        """Return flat workflow + execution summary rows for CSV/XLSX export."""
        result = await self._session.execute(
            select(
                Workflow.name,
                Workflow.is_active,
                Workflow.created_at,
                func.count(WorkflowExecution.id).label("execution_count"),
                func.sum(
                    cast(WorkflowExecution.status == ExecutionStatus.COMPLETED, Integer)
                ).label("completed"),
                func.sum(cast(WorkflowExecution.status == ExecutionStatus.FAILED, Integer)).label(
                    "failed"
                ),
            )
            .outerjoin(WorkflowExecution, WorkflowExecution.workflow_id == Workflow.id)
            .where(Workflow.deleted_at.is_(None))
            .group_by(Workflow.id, Workflow.name, Workflow.is_active, Workflow.created_at)
            .order_by(Workflow.created_at.desc())
        )
        return [
            {
                "name": r.name,
                "is_active": r.is_active,
                "execution_count": r.execution_count or 0,
                "completed": r.completed or 0,
                "failed": r.failed or 0,
                "created_at": str(r.created_at),
            }
            for r in result.all()
        ]
