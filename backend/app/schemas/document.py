"""
Document metadata Pydantic schemas.

Request and response models for document metadata endpoints.

Security rules:
  - owner_id is always taken from the authenticated user — never from the
    request body.  Client cannot impersonate another owner.
  - status / ocr_status are server-controlled and NOT accepted in any
    request body. Milestone 4 does not implement OCR or processing; the
    backend initialises both fields to PENDING on creation.
  - storage_path is set by the backend (Milestone 5 will implement actual
    upload). In Milestone 4, POST accepts it as input so metadata can be
    created without requiring a real file store.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus, OcrStatus

# =============================================================================
# Request schemas
# =============================================================================


class DocumentCreate(BaseModel):
    """
    Payload for POST /api/v1/documents.

    owner_id is derived from the authenticated user at the service layer.
    status and ocr_status are not accepted — backend sets them to PENDING.
    """

    file_name: str = Field(..., min_length=1, max_length=500, examples=["invoice_q3.pdf"])
    storage_path: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description=(
            "Storage key / path in object storage. " "Actual file upload is handled in Milestone 5."
        ),
        examples=["uploads/2024/invoice_q3.pdf"],
    )
    file_type: str | None = Field(
        default=None,
        max_length=100,
        examples=["application/pdf"],
    )
    file_size: int | None = Field(
        default=None,
        ge=0,
        description="File size in bytes.",
        examples=[204800],
    )
    checksum: str | None = Field(
        default=None,
        max_length=64,
        description="SHA-256 hex digest for integrity verification.",
        examples=["a3f4..."],
    )


class DocumentUpdate(BaseModel):
    """
    Payload for PATCH /api/v1/documents/{id}.

    Only metadata fields that a user can meaningfully change.
    status / ocr_status / storage_path / owner_id are NOT updatable via API.
    """

    file_name: str | None = Field(default=None, min_length=1, max_length=500)
    file_type: str | None = Field(default=None, max_length=100)
    checksum: str | None = Field(default=None, max_length=64)


# =============================================================================
# Response schemas
# =============================================================================


class DocumentResponse(BaseModel):
    """Document metadata response — file bytes are never included."""

    id: uuid.UUID
    file_name: str
    storage_path: str
    file_type: str | None
    file_size: int | None
    owner_id: uuid.UUID
    status: DocumentStatus
    ocr_status: OcrStatus
    checksum: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    """Envelope for successful file upload."""

    success: bool = True
    message: str = "Document uploaded successfully."
    data: DocumentResponse


class PaginatedDocumentResponse(BaseModel):
    """Paginated list response for GET /api/v1/documents."""

    success: bool = True
    message: str = "Documents retrieved successfully."
    data: list[DocumentResponse]
    meta: dict[str, int]
