"""
Employee profile API routes.

Thin route handlers — all business logic and authorization lives in
EmployeeProfileService.

Authorization is enforced SERVER-SIDE in the service layer:
  - admin / hr    : all profiles, create/update any
  - manager       : all profiles (read), cannot write others
  - employee      : own profile only (read + write)

The user_id path parameter is validated in the service — clients cannot
use it to escalate their own access.

Endpoints:
  GET   /api/v1/employees                        — list (paginated, role-scoped)
  GET   /api/v1/employees/{user_id}/profile      — get one
  POST  /api/v1/employees/{user_id}/profile      — create
  PATCH /api/v1/employees/{user_id}/profile      — update
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.employee import EmployeeProfileCreate, EmployeeProfileUpdate
from app.services.employee_profile_service import EmployeeProfileService

router = APIRouter(
    prefix="/employees",
    tags=["Employees"],
)


def _get_service(db: AsyncSession = Depends(get_db)) -> EmployeeProfileService:
    """Provide an EmployeeProfileService instance with the injected DB session."""
    return EmployeeProfileService(db)


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP address for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# =============================================================================
# GET /employees — list (role-scoped in service)
# =============================================================================


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List employee profiles",
    description=(
        "Returns a paginated list of employee profiles. "
        "admin/hr/manager see all profiles. "
        "Employees see only their own profile. "
        "Requires authentication."
    ),
    responses={
        200: {"description": "Employee profiles retrieved successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def list_employees(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page."),
    current_user: User = Depends(get_current_user),
    svc: EmployeeProfileService = Depends(_get_service),
) -> dict[str, Any]:
    """List employee profiles — scope determined by the caller's role."""
    result = await svc.list_profiles(actor=current_user, page=page, page_size=page_size)
    return {
        "success": True,
        "message": result.message,
        "data": [p.model_dump(mode="json") for p in result.data],
        "meta": result.meta,
    }


# =============================================================================
# GET /employees/{user_id}/profile — get one
# =============================================================================


@router.get(
    "/{user_id}/profile",
    status_code=status.HTTP_200_OK,
    summary="Get an employee profile",
    description=(
        "Returns the employee profile for the specified user. "
        "admin/hr/manager may access any profile. "
        "Employees may only access their own."
    ),
    responses={
        200: {"description": "Employee profile retrieved successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Access denied — not owner and insufficient role."},
        404: {"description": "Profile not found."},
    },
)
async def get_employee_profile(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: EmployeeProfileService = Depends(_get_service),
) -> dict[str, Any]:
    """Return the employee profile for the specified user UUID."""
    profile = await svc.get_profile(user_id, actor=current_user)
    return {
        "success": True,
        "message": "Employee profile retrieved successfully.",
        "data": profile.model_dump(mode="json"),
    }


# =============================================================================
# POST /employees/{user_id}/profile — create
# =============================================================================


@router.post(
    "/{user_id}/profile",
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee profile",
    description=(
        "Creates an employee profile for the specified user. "
        "admin/hr may create for any user. "
        "Employees may only create their own profile."
    ),
    responses={
        201: {"description": "Employee profile created successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient permission."},
        404: {"description": "User not found."},
        409: {"description": "Profile already exists or employee code in use."},
    },
)
async def create_employee_profile(
    user_id: uuid.UUID,
    data: EmployeeProfileCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: EmployeeProfileService = Depends(_get_service),
) -> dict[str, Any]:
    """Create an employee profile — user_id from URL, authorization in service."""
    profile = await svc.create_profile(
        user_id,
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Employee profile created successfully.",
        "data": profile.model_dump(mode="json"),
    }


# =============================================================================
# PATCH /employees/{user_id}/profile — update
# =============================================================================


@router.patch(
    "/{user_id}/profile",
    status_code=status.HTTP_200_OK,
    summary="Update an employee profile",
    description=(
        "Partially updates an employee profile. "
        "admin/hr may update any profile. "
        "Employees may only update their own."
    ),
    responses={
        200: {"description": "Employee profile updated successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient permission."},
        404: {"description": "Profile not found."},
        409: {"description": "Employee code already in use."},
    },
)
async def update_employee_profile(
    user_id: uuid.UUID,
    data: EmployeeProfileUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: EmployeeProfileService = Depends(_get_service),
) -> dict[str, Any]:
    """Partially update an employee profile — authorization enforced in service."""
    profile = await svc.update_profile(
        user_id,
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Employee profile updated successfully.",
        "data": profile.model_dump(mode="json"),
    }
