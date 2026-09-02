"""
Prediction Pydantic schemas — Phase 9.

Request and response models for the /api/v1/predictions/* endpoints.

Supported prediction models:
  - revenue_forecast      — projects next-quarter revenue from salary trends
  - employee_attrition    — estimates attrition risk from tenure and role data
  - customer_churn        — estimates churn probability from engagement patterns

All predictions are deterministic statistical approximations computed
from existing database records. No external ML library is required.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Supported model identifiers
# ---------------------------------------------------------------------------

PredictionModelName = Literal[
    "revenue_forecast",
    "employee_attrition",
    "customer_churn",
]


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class PredictionRequest(BaseModel):
    """Request body for POST /api/v1/predictions."""

    model: PredictionModelName = Field(
        ...,
        description=(
            "Which prediction model to run. "
            "One of: 'revenue_forecast', 'employee_attrition', 'customer_churn'."
        ),
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional model-specific input parameters.",
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class PredictionResponse(BaseModel):
    """Single prediction result."""

    id: uuid.UUID
    model: str
    input: dict[str, Any] | None = None
    prediction: dict[str, Any] | None = None
    confidence: float | None = None
    execution_time: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PredictionListResponse(BaseModel):
    """Paginated list of prediction history records."""

    data: list[PredictionResponse]
    meta: dict[str, int]
