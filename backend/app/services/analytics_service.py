"""
Analytics service — business logic for analytics endpoints (Phase 9).

Responsibilities:
  - Orchestrate AnalyticsRepository queries into response schemas.
  - Apply month-label formatting for chart data.
  - Generate realistic revenue proxies from salary/headcount data.
  - Return sensible empty-state responses when the database has no data.

Architecture:
  API → AnalyticsService → AnalyticsRepository → PostgreSQL

No authorization is performed here — RBAC is enforced at the API route
layer via the `require_role` dependency before this service is called.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import (
    AIUsageAnalyticsResponse,
    DepartmentAnalyticsItem,
    DepartmentAnalyticsResponse,
    DocumentAnalyticsResponse,
    EmployeeAnalyticsResponse,
    KPISummaryResponse,
    MonthlyCount,
    MonthlyRevenue,
    RevenueAnalyticsResponse,
    RoleCount,
    StatusCount,
    WorkflowAnalyticsResponse,
)

logger = logging.getLogger(__name__)

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Revenue is estimated as a multiple of salary expense (industry approximation)
_REVENUE_MULTIPLIER = 3.5


class AnalyticsService:
    """Business logic layer wrapping AnalyticsRepository for Phase 9."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the database session."""
        self._session = session
        self._repo = AnalyticsRepository(session)

    # =========================================================================
    # KPI Summary
    # =========================================================================

    async def get_kpi_summary(self) -> KPISummaryResponse:
        """Return aggregated KPI counts for the analytics overview."""
        data = await self._repo.get_kpi_summary()
        return KPISummaryResponse(**data)

    # =========================================================================
    # Revenue Analytics
    # =========================================================================

    async def get_revenue_analytics(self, year: int) -> RevenueAnalyticsResponse:
        """
        Build monthly revenue chart data for the given year.

        Revenue is estimated as salary_expenses × _REVENUE_MULTIPLIER.
        If no salary data exists, returns a zeroed 12-month skeleton so the
        frontend always has valid chart data to render.
        """
        raw = await self._repo.get_monthly_salary_totals(year)
        salary_by_month: dict[int, float] = {r["month"]: r["total_salary"] for r in raw}

        data: list[MonthlyRevenue] = []
        total_expenses = 0.0

        for i, name in enumerate(_MONTH_NAMES, start=1):
            expenses = salary_by_month.get(i, 0.0)
            # Apply a seasonal factor to make chart interesting without
            # fabricating data: use actual salary figures only.
            revenue = round(expenses * _REVENUE_MULTIPLIER, 2)
            profit = round(revenue - expenses, 2)
            total_expenses += expenses
            data.append(
                MonthlyRevenue(
                    month=name,
                    revenue=revenue,
                    expenses=round(expenses, 2),
                    profit=profit,
                )
            )

        avg_monthly = round(total_expenses / 12, 2) if total_expenses else 0.0

        return RevenueAnalyticsResponse(
            year=year,
            data=data,
            total_expenses_ytd=round(total_expenses, 2),
            avg_monthly_expenses=avg_monthly,
        )

    # =========================================================================
    # Department Analytics
    # =========================================================================

    async def get_department_analytics(self) -> DepartmentAnalyticsResponse:
        """Return per-department analytics with employee counts and salary."""
        dept_rows = await self._repo.get_department_breakdown()
        doc_by_dept = await self._repo.get_document_count_by_owner_department()
        wf_by_dept = await self._repo.get_active_workflow_count_by_creator_department()

        items: list[DepartmentAnalyticsItem] = []
        for row in dept_rows:
            dept_id_str = str(row["department_id"])
            items.append(
                DepartmentAnalyticsItem(
                    department_id=row["department_id"],  # type: ignore[arg-type]
                    department_name=row["department_name"],  # type: ignore[arg-type]
                    employee_count=row["employee_count"],  # type: ignore[arg-type]
                    avg_salary=row["avg_salary"],  # type: ignore[arg-type]
                    document_count=doc_by_dept.get(dept_id_str, 0),
                    active_workflows=wf_by_dept.get(dept_id_str, 0),
                )
            )

        return DepartmentAnalyticsResponse(
            data=items,
            total_departments=len(items),
        )

    # =========================================================================
    # Employee Analytics
    # =========================================================================

    async def get_employee_analytics(self) -> EmployeeAnalyticsResponse:
        """Return employee trend and composition data."""
        counts = await self._repo.get_employee_counts()
        role_dist = await self._repo.get_role_distribution()
        monthly = await self._repo.get_monthly_employee_headcount()

        return EmployeeAnalyticsResponse(
            total=counts["total"],
            active=counts["active"],
            new_this_month=counts["new_this_month"],
            role_distribution=[
                RoleCount(role=r["role"], count=r["count"])  # type: ignore[arg-type]
                for r in role_dist
            ],
            monthly_headcount=[
                MonthlyCount(month=r["month"], count=r["count"])  # type: ignore[arg-type]
                for r in monthly
            ],
        )

    # =========================================================================
    # Document Analytics
    # =========================================================================

    async def get_document_analytics(self) -> DocumentAnalyticsResponse:
        """Return document upload trends and status breakdown."""
        total = await self._repo.get_total_document_count()
        monthly = await self._repo.get_monthly_document_uploads()
        by_status = await self._repo.get_document_status_breakdown()
        by_ocr = await self._repo.get_document_ocr_status_breakdown()

        return DocumentAnalyticsResponse(
            total_uploads=total,
            monthly_uploads=[
                MonthlyCount(month=r["month"], count=r["count"])  # type: ignore[arg-type]
                for r in monthly
            ],
            by_status=[
                StatusCount(status=r["status"], count=r["count"])  # type: ignore[arg-type]
                for r in by_status
            ],
            by_ocr_status=[
                StatusCount(status=r["status"], count=r["count"])  # type: ignore[arg-type]
                for r in by_ocr
            ],
        )

    # =========================================================================
    # Workflow Analytics
    # =========================================================================

    async def get_workflow_analytics(self) -> WorkflowAnalyticsResponse:
        """Return workflow execution statistics."""
        total = await self._repo.get_total_execution_count()
        by_status = await self._repo.get_execution_status_breakdown()
        avg_dur = await self._repo.get_avg_execution_duration()
        step_freq = await self._repo.get_step_action_frequency()

        return WorkflowAnalyticsResponse(
            total_executions=total,
            by_status=[
                StatusCount(status=r["status"], count=r["count"])  # type: ignore[arg-type]
                for r in by_status
            ],
            avg_duration_seconds=avg_dur,
            step_action_frequency=[
                StatusCount(status=r["status"], count=r["count"])  # type: ignore[arg-type]
                for r in step_freq
            ],
        )

    # =========================================================================
    # AI Usage Analytics
    # =========================================================================

    async def get_ai_usage_analytics(self) -> AIUsageAnalyticsResponse:
        """Return AI conversation usage trends."""
        stats = await self._repo.get_ai_usage_stats()
        monthly = await self._repo.get_monthly_ai_conversations()

        return AIUsageAnalyticsResponse(
            total_conversations=stats["total_conversations"],  # type: ignore[arg-type]
            monthly_conversations=[
                MonthlyCount(month=r["month"], count=r["count"])  # type: ignore[arg-type]
                for r in monthly
            ],
            avg_response_time_seconds=stats["avg_response_time_seconds"],  # type: ignore[arg-type]
            total_prompt_tokens=stats["total_prompt_tokens"],  # type: ignore[arg-type]
            total_completion_tokens=stats["total_completion_tokens"],  # type: ignore[arg-type]
        )
