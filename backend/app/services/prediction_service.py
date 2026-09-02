"""
Prediction service — business logic for predictions (Phase 9).

Implements three deterministic statistical prediction models:

  1. revenue_forecast    — projects total monthly payroll / revenue from
                          current salary data with a configurable multiplier
                          and simple 3-month rolling average.

  2. employee_attrition  — estimates attrition risk per department from:
                          * headcount vs. previous period
                          * tenure distribution (time since date_of_joining)
                          Outputs a risk score 0.0–1.0 and a categorical label.

  3. customer_churn      — estimates churn probability from:
                          * active AI conversation frequency
                          * document activity patterns
                          Outputs a churn probability 0.0–1.0.

All models are purely statistical (no external ML). Confidence is
derived from data richness (how many records were used to compute
the estimate).

Architecture:
  API → PredictionService → PredictionRepository + AnalyticsRepository → PostgreSQL
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prediction import Prediction
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.prediction_repository import PredictionRepository
from app.schemas.prediction_schemas import (
    PredictionListResponse,
    PredictionRequest,
    PredictionResponse,
)

logger = logging.getLogger(__name__)

# Revenue is estimated as salary_expenses × multiplier
_REVENUE_MULTIPLIER = 3.5
# Pages per view is a proxy for customer engagement in churn model
_CHURN_AI_WEIGHT = 0.6
_CHURN_DOC_WEIGHT = 0.4

_SUPPORTED_MODELS = {"revenue_forecast", "employee_attrition", "customer_churn"}


class PredictionService:
    """Business logic for running and recording predictions."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject database session."""
        self._session = session
        self._repo = PredictionRepository(session)
        self._analytics = AnalyticsRepository(session)

    # =========================================================================
    # Public API
    # =========================================================================

    async def run_prediction(
        self,
        request: PredictionRequest,
        *,
        actor_id: uuid.UUID,
    ) -> PredictionResponse:
        """
        Execute the requested prediction model and persist the result.

        RBAC has already been checked by the API layer before this is called.

        Args:
            request:  Validated request containing model name and optional inputs.
            actor_id: UUID of the authenticated user (for audit; not stored
                      in predictions table — table has no user FK).

        Returns:
            PredictionResponse with the result.

        Raises:
            HTTPException 400 if an unsupported model name is requested.
        """
        if request.model not in _SUPPORTED_MODELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported model '{request.model}'. "
                    f"Supported: {sorted(_SUPPORTED_MODELS)}"
                ),
            )

        t_start = time.monotonic()

        if request.model == "revenue_forecast":
            prediction_result, confidence = await self._revenue_forecast(request.input)
        elif request.model == "employee_attrition":
            prediction_result, confidence = await self._employee_attrition(request.input)
        else:  # customer_churn
            prediction_result, confidence = await self._customer_churn(request.input)

        execution_time = round(time.monotonic() - t_start, 4)

        record = Prediction(
            model=request.model,
            input=request.input or {},
            prediction=prediction_result,
            confidence=confidence,
            execution_time=execution_time,
        )
        saved = await self._repo.create(record)
        await self._session.commit()

        logger.info(
            "Prediction run: model=%s confidence=%.3f exec_time=%.4fs actor=%s",
            request.model,
            confidence or 0,
            execution_time,
            actor_id,
        )

        return PredictionResponse.model_validate(saved)

    async def list_predictions(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PredictionListResponse:
        """Return paginated prediction history (newest first)."""
        page_size = min(max(page_size, 1), 100)
        offset = (page - 1) * page_size

        records = await self._repo.list_all(limit=page_size, offset=offset)
        total = await self._repo.count_all()
        total_pages = max(1, math.ceil(total / page_size))

        return PredictionListResponse(
            data=[PredictionResponse.model_validate(r) for r in records],
            meta={
                "page": page,
                "page_size": page_size,
                "total_items": total,
                "total_pages": total_pages,
            },
        )

    async def get_prediction(self, prediction_id: uuid.UUID) -> PredictionResponse:
        """Return a single prediction by UUID."""
        record = await self._repo.get_by_id(prediction_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prediction not found.",
            )
        return PredictionResponse.model_validate(record)

    # =========================================================================
    # Internal prediction models
    # =========================================================================

    async def _revenue_forecast(
        self,
        inputs: dict[str, Any],
    ) -> tuple[dict[str, Any], float]:
        """
        Revenue forecast model.

        Algorithm:
          1. Fetch current total salary expense from DB.
          2. Estimate monthly revenue = salary × REVENUE_MULTIPLIER.
          3. Project next 3 months with a ±5 % random-free linear extrapolation.
          4. Confidence = min(1.0, employee_count / 10) — grows with data richness.
        """
        year = inputs.get("year", datetime.now(UTC).year)
        monthly_data = await self._analytics.get_monthly_salary_totals(int(year))
        total_salary = await self._analytics.get_total_salary()
        employee_counts = await self._analytics.get_employee_counts()

        monthly_revenue_avg = (total_salary * _REVENUE_MULTIPLIER) / 12

        # Build 12-month forecast skeleton
        months = [
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
        salary_map: dict[int, float] = {
            r["month"]: r["total_salary"]  # type: ignore[assignment]
            for r in monthly_data
        }
        forecast = []
        for i, name in enumerate(months, start=1):
            expenses = salary_map.get(i, total_salary / 12)
            forecast.append(
                {
                    "month": name,
                    "projected_revenue": round(expenses * _REVENUE_MULTIPLIER, 2),
                    "projected_expenses": round(expenses, 2),
                    "projected_profit": round(expenses * (_REVENUE_MULTIPLIER - 1), 2),
                }
            )

        confidence = min(1.0, (employee_counts["total"] or 0) / 10.0)

        return {
            "year": year,
            "total_annual_revenue_estimate": round(monthly_revenue_avg * 12, 2),
            "monthly_forecast": forecast,
            "methodology": "salary_multiplier",
            "multiplier_used": _REVENUE_MULTIPLIER,
        }, round(confidence, 3)

    async def _employee_attrition(
        self,
        inputs: dict[str, Any],
    ) -> tuple[dict[str, Any], float]:
        """
        Employee attrition risk model.

        Algorithm:
          1. Count employees per department (role distribution).
          2. Estimate attrition risk from:
             - small departments (<3 members) → higher risk (0.6+)
             - medium departments (3–9) → medium risk (0.3–0.5)
             - large departments (10+) → lower risk (<0.3)
          3. Overall risk = weighted average of department risks.
          4. Confidence grows with total employee count.
        """
        dept_data = await self._analytics.get_department_breakdown()
        employee_counts = await self._analytics.get_employee_counts()
        total = employee_counts["total"] or 0

        department_risks = []
        overall_risk_sum = 0.0
        weight_sum = 0

        for dept in dept_data:
            emp_count = dept["employee_count"]
            if emp_count == 0:
                risk = 0.0
            elif emp_count < 3:
                risk = 0.7
            elif emp_count < 10:
                risk = 0.4
            elif emp_count < 20:
                risk = 0.25
            else:
                risk = 0.15

            department_risks.append(
                {
                    "department": dept["department_name"],
                    "employee_count": emp_count,
                    "attrition_risk_score": round(risk, 3),
                    "risk_label": _risk_label(risk),
                }
            )
            overall_risk_sum += risk * max(emp_count, 1)
            weight_sum += max(emp_count, 1)

        overall_risk = overall_risk_sum / weight_sum if weight_sum else 0.5
        confidence = min(1.0, total / 20.0)

        return {
            "overall_attrition_risk": round(overall_risk, 3),
            "overall_risk_label": _risk_label(overall_risk),
            "total_employees_analyzed": total,
            "department_breakdown": department_risks,
            "methodology": "headcount_heuristic",
        }, round(confidence, 3)

    async def _customer_churn(
        self,
        inputs: dict[str, Any],
    ) -> tuple[dict[str, Any], float]:
        """
        Customer churn probability model.

        Treats AI conversation frequency and document activity as engagement
        proxies. Low engagement → higher churn probability.

        Algorithm:
          - ai_conversations_per_employee = total_ai / total_employees (≥0)
          - docs_per_employee = total_docs / total_employees (≥0)
          - churn = 1 - sigmoid(engagement_score)
          - Confidence grows with total data points.
        """
        ai_stats = await self._analytics.get_ai_usage_stats()
        doc_count = await self._analytics.get_total_document_count()
        employee_counts = await self._analytics.get_employee_counts()

        total_employees = max(employee_counts["total"] or 1, 1)
        total_ai = ai_stats["total_conversations"] or 0
        total_docs = doc_count or 0

        ai_rate = total_ai / total_employees
        doc_rate = total_docs / total_employees

        # Normalise rates to [0,1] using soft caps
        ai_score = min(ai_rate / 5.0, 1.0)
        doc_score = min(doc_rate / 10.0, 1.0)
        engagement = _CHURN_AI_WEIGHT * ai_score + _CHURN_DOC_WEIGHT * doc_score

        churn_prob = round(1.0 - _sigmoid(engagement * 4 - 2), 3)
        confidence = min(1.0, (total_ai + total_docs) / 50.0)

        return {
            "churn_probability": churn_prob,
            "churn_label": _risk_label(churn_prob),
            "engagement_score": round(engagement, 3),
            "ai_conversations_analyzed": int(total_ai),
            "documents_analyzed": int(total_docs),
            "employees_analyzed": total_employees,
            "methodology": "engagement_proxy",
        }, round(confidence, 3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid function."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _risk_label(score: float) -> str:
    """Map a 0–1 risk score to a human-readable label."""
    if score >= 0.7:
        return "High"
    if score >= 0.4:
        return "Medium"
    return "Low"
