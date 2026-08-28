"""
OCR Job status tracking API routes.

Provides endpoints for:
  - GET /api/v1/ocr/jobs/{job_id} — poll asynchronous OCR task state
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.services.ocr_service import OCRService

router = APIRouter(
    prefix="/ocr",
    tags=["OCR"],
)


def _get_ocr_service(db: AsyncSession = Depends(get_db)) -> OCRService:
    """Provide an OCRService instance with the injected DB session."""
    return OCRService(db)


@router.get(
    "/jobs/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Get OCR job status",
    description="Returns current Celery task execution state (PENDING, PROCESSING, COMPLETED, FAILED).",
    responses={
        200: {"description": "Job status retrieved successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def get_ocr_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    svc: OCRService = Depends(_get_ocr_service),
) -> dict[str, Any]:
    """Poll Celery task status for an asynchronous OCR extraction job."""
    result = await svc.get_ocr_job_status(job_id=job_id, actor=current_user)
    return {
        "success": True,
        "message": "OCR job status retrieved.",
        "data": result,
    }
