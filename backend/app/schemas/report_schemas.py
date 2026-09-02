"""
Report Pydantic schemas — Phase 9.

Request and response models for the /api/v1/reports/* endpoints.

Reports are generated asynchronously via Celery. The API returns
immediately with status=pending; clients poll GET /reports/{id} for
status updates.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.report import ReportStatus

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

ReportTypeName = Literal[
    "revenue",
    "employees",
    "departments",
    "workflows",
    "documents",
    "ai_usage",
]

ReportFormatName = Literal["csv", "xlsx", "pdf"]


class ReportGenerateRequest(BaseModel):
    """Request body for POST /api/v1/reports."""

    report_type: ReportTypeName = Field(
        ...,
        description=(
            "Type of report to generate. "
            "One of: 'revenue', 'employees', 'departments', 'workflows', "
            "'documents', 'ai_usage'."
        ),
    )
    format: ReportFormatName = Field(
        "csv",
        description="Output format. One of: 'csv', 'xlsx', 'pdf'.",
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional filters (e.g. {'year': 2026}).",
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class ReportResponse(BaseModel):
    """Single report record."""

    id: uuid.UUID
    report_type: str
    format: str | None = None
    status: ReportStatus
    file_path: str | None = None
    generated_by: uuid.UUID | None = None
    generated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    """Paginated list of report records."""

    data: list[ReportResponse]
    meta: dict[str, int]
