"""
Predictions API routes — Phase 9.

Endpoints:
  POST /api/v1/predictions         — Run a prediction model
  GET  /api/v1/predictions         — List prediction history (paginated)
  GET  /api/v1/predictions/{id}    — Get a single prediction

Access:
  POST: admin, manager, finance, hr roles (analyst-capable roles)
  GET:  admin, manager, finance, hr roles

All routes require JWT authentication.
RBAC is enforced via require_role() dependency before the service is called.
Route handlers are thin: validate → delegate → respond.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.user import User
from app.schemas.prediction_schemas import PredictionRequest
from app.services.prediction_service import PredictionService

router = APIRouter(prefix="/predictions", tags=["Predictions"])

_PREDICTION_ROLES = ("admin", "manager", "finance", "hr")


def _get_service(db: AsyncSession = Depends(get_db)) -> PredictionService:
    """Provide a PredictionService with the injected DB session."""
    return PredictionService(db)


# ---------------------------------------------------------------------------
# Run a prediction
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Run a prediction model",
    description=(
        "Executes a deterministic statistical prediction model and persists "
        "the result. Supported models: 'revenue_forecast', 'employee_attrition', "
        "'customer_churn'. Requires admin, manager, finance, or hr role."
    ),
    responses={
        201: {"description": "Prediction completed successfully."},
        400: {"description": "Unsupported model name."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        422: {"description": "Validation error."},
    },
)
async def run_prediction(
    data: PredictionRequest,
    current_user: User = Depends(require_role(*_PREDICTION_ROLES)),
    svc: PredictionService = Depends(_get_service),
) -> dict[str, Any]:
    """Execute the prediction model and return the result."""
    result = await svc.run_prediction(data, actor_id=current_user.id)
    return {
        "success": True,
        "message": "Prediction completed successfully.",
        "data": result.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# List prediction history
# ---------------------------------------------------------------------------


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List prediction history",
    description=(
        "Returns a paginated list of all prediction records, newest first. "
        "Requires admin, manager, finance, or hr role."
    ),
    responses={
        200: {"description": "Predictions retrieved successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
    },
)
async def list_predictions(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page."),
    current_user: User = Depends(require_role(*_PREDICTION_ROLES)),
    svc: PredictionService = Depends(_get_service),
) -> dict[str, Any]:
    """List prediction history with pagination."""
    result = await svc.list_predictions(page=page, page_size=page_size)
    return {
        "success": True,
        "message": "Predictions retrieved successfully.",
        "data": [r.model_dump(mode="json") for r in result.data],
        "meta": result.meta,
    }


# ---------------------------------------------------------------------------
# Get single prediction
# ---------------------------------------------------------------------------


@router.get(
    "/{prediction_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a prediction by ID",
    description=(
        "Returns a single prediction record by UUID. "
        "Requires admin, manager, finance, or hr role."
    ),
    responses={
        200: {"description": "Prediction retrieved successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        404: {"description": "Prediction not found."},
    },
)
async def get_prediction(
    prediction_id: uuid.UUID,
    current_user: User = Depends(require_role(*_PREDICTION_ROLES)),
    svc: PredictionService = Depends(_get_service),
) -> dict[str, Any]:
    """Return a single prediction by UUID."""
    result = await svc.get_prediction(prediction_id)
    return {
        "success": True,
        "message": "Prediction retrieved successfully.",
        "data": result.model_dump(mode="json"),
    }
