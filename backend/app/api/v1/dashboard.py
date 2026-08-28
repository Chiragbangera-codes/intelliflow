"""
Dashboard API routes.

Single endpoint returning KPI counts for the authenticated dashboard.

Stats included (Milestone 4 only):
  - total_departments : active department count (all roles)
  - total_employees   : active employee profile count (all roles)
  - total_documents   : active documents (admin/hr → global; others → own)

Future milestones will add revenue, workflow, AI, and notification stats.
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


def _get_service(db: AsyncSession = Depends(get_db)) -> DashboardService:
    """Provide a DashboardService instance with the injected DB session."""
    return DashboardService(db)


@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    summary="Get dashboard statistics",
    description=(
        "Returns key metrics for the authenticated user's dashboard. "
        "Document count is scoped by role: admin/hr see all documents, "
        "other roles see only their own. "
        "Requires authentication."
    ),
    responses={
        200: {"description": "Dashboard statistics retrieved successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    svc: DashboardService = Depends(_get_service),
) -> dict[str, Any]:
    """Return dashboard KPI counts from the database."""
    stats = await svc.get_stats(actor=current_user)
    return {
        "success": True,
        "message": "Dashboard statistics retrieved successfully.",
        "data": stats.model_dump(mode="json"),
    }
