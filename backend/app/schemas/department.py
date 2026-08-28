"""
Department Pydantic schemas.

Request and response models for all department endpoints.

Security rules:
  - id and timestamps are read-only; never accepted in request bodies.
  - Response models use from_attributes=True so ORM objects are passed directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# =============================================================================
# Request schemas
# =============================================================================


class DepartmentCreate(BaseModel):
    """Payload for POST /api/v1/departments."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        examples=["Engineering"],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        examples=["Product engineering department."],
    )


class DepartmentUpdate(BaseModel):
    """Payload for PATCH /api/v1/departments/{id}. All fields optional."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        examples=["Engineering"],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        examples=["Updated description."],
    )


# =============================================================================
# Response schemas
# =============================================================================


class DepartmentResponse(BaseModel):
    """Single department returned from list/get/create/update endpoints."""

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDepartmentResponse(BaseModel):
    """Paginated list response for GET /api/v1/departments."""

    success: bool = True
    message: str = "Departments retrieved successfully."
    data: list[DepartmentResponse]
    meta: dict[str, int]
