"""
Department API routes.

Thin route handlers — all business logic lives in DepartmentService.

RBAC:
  GET  (list/get) — all authenticated users
  POST / PATCH / DELETE — admin, hr only

Endpoints:
  GET    /api/v1/departments          — list (paginated)
  GET    /api/v1/departments/{id}     — get one
  POST   /api/v1/departments          — create
  PATCH  /api/v1/departments/{id}     — update
  DELETE /api/v1/departments/{id}     — soft-delete
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.user import User
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.services.department_service import DepartmentService

router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
)


def _get_service(db: AsyncSession = Depends(get_db)) -> DepartmentService:
    """Provide a DepartmentService instance with the injected DB session."""
    return DepartmentService(db)


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP address from the request for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# =============================================================================
# GET /departments — list (all authenticated users)
# =============================================================================


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List all departments",
    description=(
        "Returns a paginated list of active departments. "
        "Requires authentication. All roles may access this endpoint."
    ),
    responses={
        200: {"description": "Departments retrieved successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def list_departments(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page."),
    _current_user: User = Depends(get_current_user),
    svc: DepartmentService = Depends(_get_service),
) -> dict[str, Any]:
    """List all active departments with pagination."""
    data, meta = await svc.list_departments(page=page, page_size=page_size)
    return {
        "success": True,
        "message": "Departments retrieved successfully.",
        "data": [d.model_dump(mode="json") for d in data],
        "meta": meta,
    }


# =============================================================================
# GET /departments/{department_id} — get one (all authenticated users)
# =============================================================================


@router.get(
    "/{department_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a department by ID",
    description="Returns a single active department. Requires authentication.",
    responses={
        200: {"description": "Department retrieved successfully."},
        401: {"description": "Not authenticated."},
        404: {"description": "Department not found."},
    },
)
async def get_department(
    department_id: uuid.UUID,
    _current_user: User = Depends(get_current_user),
    svc: DepartmentService = Depends(_get_service),
) -> dict[str, Any]:
    """Return a single department by UUID."""
    dept = await svc.get_department(department_id)
    return {
        "success": True,
        "message": "Department retrieved successfully.",
        "data": dept.model_dump(mode="json"),
    }


# =============================================================================
# POST /departments — create (admin, hr only)
# =============================================================================


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new department",
    description=(
        "Creates a new department. "
        "Requires admin or hr role. "
        "Returns 409 if a department with the same name already exists."
    ),
    responses={
        201: {"description": "Department created successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role (admin or hr required)."},
        409: {"description": "Department name already exists."},
    },
)
async def create_department(
    data: DepartmentCreate,
    request: Request,
    current_user: User = Depends(require_role("admin", "hr")),
    svc: DepartmentService = Depends(_get_service),
) -> dict[str, Any]:
    """Create a new department (admin/hr only)."""
    dept = await svc.create_department(
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Department created successfully.",
        "data": dept.model_dump(mode="json"),
    }


# =============================================================================
# PATCH /departments/{department_id} — update (admin, hr only)
# =============================================================================


@router.patch(
    "/{department_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a department",
    description=(
        "Partially updates a department's name and/or description. " "Requires admin or hr role."
    ),
    responses={
        200: {"description": "Department updated successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        404: {"description": "Department not found."},
        409: {"description": "Department name already exists."},
    },
)
async def update_department(
    department_id: uuid.UUID,
    data: DepartmentUpdate,
    request: Request,
    current_user: User = Depends(require_role("admin", "hr")),
    svc: DepartmentService = Depends(_get_service),
) -> dict[str, Any]:
    """Partially update a department (admin/hr only)."""
    dept = await svc.update_department(
        department_id,
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Department updated successfully.",
        "data": dept.model_dump(mode="json"),
    }


# =============================================================================
# DELETE /departments/{department_id} — soft-delete (admin, hr only)
# =============================================================================


@router.delete(
    "/{department_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a department",
    description=(
        "Soft-deletes a department (sets deleted_at). "
        "Physical deletion is blocked by the database FK if active users exist. "
        "Requires admin or hr role."
    ),
    responses={
        200: {"description": "Department deleted successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        404: {"description": "Department not found."},
    },
)
async def delete_department(
    department_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_role("admin", "hr")),
    svc: DepartmentService = Depends(_get_service),
) -> dict[str, Any]:
    """Soft-delete a department (admin/hr only)."""
    await svc.delete_department(
        department_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Department deleted successfully.",
    }
