"""
Employee profile Pydantic schemas.

Request and response models for employee profile endpoints.

Security rules:
  - user_id is always taken from the authenticated user or URL path — never
    from the request body.
  - Salary and sensitive HR fields are included but access is gated by RBAC
    at the service layer.
  - password_hash is never present in any employee response.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# =============================================================================
# Request schemas
# =============================================================================


class EmployeeProfileCreate(BaseModel):
    """
    Payload for POST /api/v1/employees/{user_id}/profile.

    user_id is taken from the URL — not from this body.
    """

    employee_code: str | None = Field(
        default=None,
        max_length=50,
        examples=["EMP-0042"],
    )
    date_of_joining: date | None = Field(
        default=None,
        examples=["2024-01-15"],
    )
    designation: str | None = Field(
        default=None,
        max_length=200,
        examples=["Senior Software Engineer"],
    )
    salary: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        examples=["95000.00"],
    )
    manager_id: uuid.UUID | None = Field(
        default=None,
        description="UUID of the manager user (users.id — not employee_profiles.id).",
    )
    emergency_contact: str | None = Field(
        default=None,
        max_length=500,
        examples=["Jane Doe — +1-555-0100"],
    )
    address: str | None = Field(
        default=None,
        max_length=2000,
        examples=["123 Main St, Springfield, IL 62701"],
    )
    profile_photo: str | None = Field(
        default=None,
        max_length=1000,
        description="Storage path or URL for the profile photo.",
    )


class EmployeeProfileUpdate(BaseModel):
    """
    Payload for PATCH /api/v1/employees/{user_id}/profile.

    All fields optional — only provided fields are updated.
    """

    employee_code: str | None = Field(default=None, max_length=50)
    date_of_joining: date | None = None
    designation: str | None = Field(default=None, max_length=200)
    salary: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    manager_id: uuid.UUID | None = None
    emergency_contact: str | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=2000)
    profile_photo: str | None = Field(default=None, max_length=1000)


# =============================================================================
# Response schemas
# =============================================================================


class EmployeeProfileResponse(BaseModel):
    """
    Employee profile with embedded user info.

    Never includes password_hash. Salary is included because
    access to this endpoint is role-gated.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    employee_code: str | None
    date_of_joining: date | None
    designation: str | None
    salary: Decimal | None
    manager_id: uuid.UUID | None
    emergency_contact: str | None
    address: str | None
    profile_photo: str | None
    created_at: datetime
    updated_at: datetime

    # Embedded user fields for convenience
    first_name: str
    last_name: str
    email: str
    role: str

    model_config = {"from_attributes": True}


class PaginatedEmployeeResponse(BaseModel):
    """Paginated list response for GET /api/v1/employees."""

    success: bool = True
    message: str = "Employee profiles retrieved successfully."
    data: list[EmployeeProfileResponse]
    meta: dict[str, int]
