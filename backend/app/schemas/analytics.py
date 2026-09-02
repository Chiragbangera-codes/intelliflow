"""
Analytics Pydantic schemas — Phase 9.

All response models for the /api/v1/analytics/* endpoints.

Design decisions:
  - All monetary values are float (Python) rather than Decimal to keep
    JSON serialisation simple; analytics are approximations, not accounting.
  - month labels use 3-letter abbreviations ("Jan", "Feb", …) for chart
    axis labels.
  - Optional fields use sensible defaults so empty-database queries never
    return None where the frontend expects a number.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class MonthlyCount(BaseModel):
    """A (month-label, count) data point for trend charts."""

    month: str = Field(..., description="3-letter month abbreviation: 'Jan'…'Dec'.")
    count: int = Field(0, ge=0)


class MonthlyRevenue(BaseModel):
    """Monthly revenue/expense data point for the revenue chart."""

    month: str = Field(..., description="3-letter month abbreviation.")
    revenue: float = Field(0.0, ge=0)
    expenses: float = Field(0.0, ge=0)
    profit: float = Field(0.0)


class RoleCount(BaseModel):
    """Role name + member count for the role-distribution chart."""

    role: str
    count: int = Field(0, ge=0)


class StatusCount(BaseModel):
    """Generic status + count pair."""

    status: str
    count: int = Field(0, ge=0)


# ---------------------------------------------------------------------------
# KPI Summary (dashboard header)
# ---------------------------------------------------------------------------


class KPISummaryResponse(BaseModel):
    """Aggregated top-level KPIs for the analytics overview cards."""

    total_employees: int = 0
    total_documents: int = 0
    active_workflows: int = 0
    total_ai_conversations: int = 0
    completed_workflow_executions: int = 0
    total_predictions_run: int = 0
    total_reports_generated: int = 0


# ---------------------------------------------------------------------------
# Revenue Analytics
# ---------------------------------------------------------------------------


class RevenueAnalyticsResponse(BaseModel):
    """Monthly revenue trend for the selected year."""

    year: int
    data: list[MonthlyRevenue]
    total_expenses_ytd: float = 0.0
    avg_monthly_expenses: float = 0.0


# ---------------------------------------------------------------------------
# Department Analytics
# ---------------------------------------------------------------------------


class DepartmentAnalyticsItem(BaseModel):
    """Per-department breakdown row."""

    department_id: uuid.UUID
    department_name: str
    employee_count: int = 0
    avg_salary: float = 0.0
    document_count: int = 0
    active_workflows: int = 0


class DepartmentAnalyticsResponse(BaseModel):
    """Collection of department analytics items."""

    data: list[DepartmentAnalyticsItem]
    total_departments: int = 0


# ---------------------------------------------------------------------------
# Employee Analytics
# ---------------------------------------------------------------------------


class EmployeeAnalyticsResponse(BaseModel):
    """Employee trend and composition data."""

    total: int = 0
    active: int = 0
    new_this_month: int = 0
    role_distribution: list[RoleCount] = []
    monthly_headcount: list[MonthlyCount] = []


# ---------------------------------------------------------------------------
# Document Analytics
# ---------------------------------------------------------------------------


class DocumentAnalyticsResponse(BaseModel):
    """Document upload trends and status breakdown."""

    total_uploads: int = 0
    monthly_uploads: list[MonthlyCount] = []
    by_status: list[StatusCount] = []
    by_ocr_status: list[StatusCount] = []


# ---------------------------------------------------------------------------
# Workflow Analytics
# ---------------------------------------------------------------------------


class WorkflowAnalyticsResponse(BaseModel):
    """Workflow execution statistics."""

    total_executions: int = 0
    by_status: list[StatusCount] = []
    avg_duration_seconds: float = 0.0
    step_action_frequency: list[StatusCount] = []


# ---------------------------------------------------------------------------
# AI Usage Analytics
# ---------------------------------------------------------------------------


class AIUsageAnalyticsResponse(BaseModel):
    """AI conversation usage trends."""

    total_conversations: int = 0
    monthly_conversations: list[MonthlyCount] = []
    avg_response_time_seconds: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
