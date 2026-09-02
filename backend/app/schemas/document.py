"""
Document metadata, versioning, sharing, lifecycle, bulk operations, and AI schemas (Milestone 11).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.document import (
    DocumentConfidentiality,
    DocumentLifecycleStatus,
    DocumentStatus,
    OcrStatus,
)
from app.models.document_share import DocumentSharePermission
from app.schemas.search import SearchResult

# =============================================================================
# Document Metadata Schemas
# =============================================================================


class DocumentCreate(BaseModel):
    """Payload for creating a document metadata record."""

    file_name: str = Field(..., min_length=1, max_length=500)
    storage_path: str = Field(..., min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    document_type: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list)
    department_id: uuid.UUID | None = None
    confidentiality: DocumentConfidentiality = DocumentConfidentiality.INTERNAL
    retention_period_days: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    file_type: str | None = Field(default=None, max_length=100)
    file_size: int | None = Field(default=None, ge=0)
    checksum: str | None = Field(default=None, max_length=64)


class DocumentUpdate(BaseModel):
    """Payload for updating document metadata."""

    file_name: str | None = Field(default=None, min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    document_type: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = None
    department_id: uuid.UUID | None = None
    confidentiality: DocumentConfidentiality | None = None
    retention_period_days: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    file_type: str | None = Field(default=None, max_length=100)
    checksum: str | None = Field(default=None, max_length=64)


class DocumentResponse(BaseModel):
    """Full enterprise document metadata response."""

    id: uuid.UUID
    file_name: str
    title: str | None = None
    description: str | None = None
    category: str | None = None
    document_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    storage_path: str
    file_type: str | None = None
    file_size: int | None = None
    owner_id: uuid.UUID
    department_id: uuid.UUID | None = None
    confidentiality: DocumentConfidentiality = DocumentConfidentiality.INTERNAL
    lifecycle_status: DocumentLifecycleStatus = DocumentLifecycleStatus.ACTIVE
    status: DocumentStatus
    ocr_status: OcrStatus
    checksum: str | None = None
    retention_period_days: int | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version_count: int = 1
    current_version_number: int = 1
    user_permission: str | None = None

    model_config = {"from_attributes": True}


class PaginatedDocumentResponse(BaseModel):
    """Paginated list envelope for document responses."""

    success: bool = True
    message: str = "Documents retrieved successfully."
    data: list[DocumentResponse]
    meta: dict[str, int]


# =============================================================================
# Version Schemas
# =============================================================================


class DocumentVersionResponse(BaseModel):
    """Single revision/version of a document."""

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    file_name: str
    storage_path: str
    file_type: str | None = None
    file_size: int | None = None
    checksum: str | None = None
    created_by: uuid.UUID
    is_current: bool
    change_summary: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionListResponse(BaseModel):
    """List of versions for a document."""

    success: bool = True
    message: str = "Document versions retrieved successfully."
    data: list[DocumentVersionResponse]
    total_versions: int


# =============================================================================
# Share Schemas
# =============================================================================


class DocumentShareCreate(BaseModel):
    """Request payload to share a document with a user."""

    user_id: uuid.UUID = Field(..., description="UUID of grantee user.")
    permission: DocumentSharePermission = Field(
        DocumentSharePermission.VIEW,
        description="Permission level: view | download | edit | manage",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiration timestamp for the access grant.",
    )


class DocumentShareUpdate(BaseModel):
    """Request payload to update an existing share."""

    permission: DocumentSharePermission | None = None
    expires_at: datetime | None = None


class DocumentShareResponse(BaseModel):
    """Single document access grant response."""

    id: uuid.UUID
    document_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    user_name: str | None = None
    granted_by: uuid.UUID
    grantor_name: str | None = None
    permission: DocumentSharePermission
    expires_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}


# =============================================================================
# Bulk Operations Schemas
# =============================================================================


class BulkDocumentIdsRequest(BaseModel):
    """Base payload containing a list of document IDs."""

    document_ids: list[uuid.UUID] = Field(..., min_length=1)

    @field_validator("document_ids")
    @classmethod
    def validate_ids_not_empty(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not v:
            raise ValueError("document_ids list cannot be empty.")
        return list(dict.fromkeys(v))  # deduplicate


class BulkTagRequest(BulkDocumentIdsRequest):
    """Payload to add tags to multiple documents."""

    tags: list[str] = Field(..., min_length=1)
    replace: bool = Field(default=False, description="Replace existing tags instead of appending.")


class BulkShareRequest(BulkDocumentIdsRequest):
    """Payload to share multiple documents with a single user."""

    user_id: uuid.UUID = Field(..., description="Grantee user.")
    permission: DocumentSharePermission = DocumentSharePermission.VIEW
    expires_at: datetime | None = None


class BulkOperationResultItem(BaseModel):
    """Itemized result for an individual document in a bulk operation."""

    document_id: uuid.UUID
    success: bool
    reason: str | None = None


class BulkOperationResponse(BaseModel):
    """Response envelope for bulk document operations."""

    success: bool = True
    message: str
    total: int
    succeeded: int
    failed: int
    results: list[BulkOperationResultItem]


# =============================================================================
# Document AI Schemas
# =============================================================================


class DocumentAISummaryResponse(BaseModel):
    """Summary generated by LLM for a specific document."""

    document_id: uuid.UUID
    document_name: str
    summary: str
    chunks_used: int
    sources: list[SearchResult] = Field(default_factory=list)


class DocumentAIChatRequest(BaseModel):
    """Request payload for conversational Q&A scoped to a single document."""

    message: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    conversation_id: uuid.UUID | None = None


class DocumentAIChatResponse(BaseModel):
    """Conversational Q&A response scoped to a single document."""

    document_id: uuid.UUID
    document_name: str
    answer: str
    conversation_id: uuid.UUID
    sources: list[SearchResult] = Field(default_factory=list)


# =============================================================================
# Document Activity Schemas
# =============================================================================


class DocumentActivityItem(BaseModel):
    """Single sanitized audit event on a document timeline."""

    id: uuid.UUID
    action: str
    actor_id: uuid.UUID
    actor_name: str | None = None
    actor_email: str | None = None
    timestamp: datetime
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class DocumentActivityResponse(BaseModel):
    """Paginated activity timeline response."""

    success: bool = True
    document_id: uuid.UUID
    data: list[DocumentActivityItem]
    total_events: int
