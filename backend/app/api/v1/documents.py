"""
Document management & intelligence API routes (Milestone 11).

Endpoints:
  Upload & Ingestion:
    POST   /api/v1/documents/upload                  — multipart streaming file upload with version 1
    POST   /api/v1/documents                         — create metadata record

  Bulk Operations (Must precede /{document_id}):
    POST   /api/v1/documents/bulk/archive            — bulk archive
    POST   /api/v1/documents/bulk/restore            — bulk restore
    POST   /api/v1/documents/bulk/delete             — bulk soft-delete
    POST   /api/v1/documents/bulk/tag                — bulk tag
    POST   /api/v1/documents/bulk/share              — bulk share

  Document Listings & Details:
    GET    /api/v1/documents                         — list documents with advanced filters & search
    GET    /api/v1/documents/{document_id}           — get document metadata
    PATCH  /api/v1/documents/{document_id}           — update metadata
    DELETE /api/v1/documents/{document_id}           — soft-delete document

  Download & Preview:
    GET    /api/v1/documents/{document_id}/download  — stream download current version
    GET    /api/v1/documents/{document_id}/preview   — stream preview current version

  Lifecycle Actions:
    POST   /api/v1/documents/{document_id}/activate  — activate document
    POST   /api/v1/documents/{document_id}/archive   — archive document
    POST   /api/v1/documents/{document_id}/restore   — restore document
    POST   /api/v1/documents/{document_id}/expire    — expire document

  Version Management:
    POST   /api/v1/documents/{document_id}/versions                       — upload new version
    GET    /api/v1/documents/{document_id}/versions                       — list all versions
    GET    /api/v1/documents/{document_id}/versions/{version_id}          — get version metadata
    POST   /api/v1/documents/{document_id}/versions/{version_id}/restore  — restore version
    GET    /api/v1/documents/{document_id}/versions/{version_id}/download — download version

  Access Grants & Sharing:
    POST   /api/v1/documents/{document_id}/shares                         — grant access to user
    GET    /api/v1/documents/{document_id}/shares                         — list active grants
    PATCH  /api/v1/documents/{document_id}/shares/{share_id}              — update grant
    DELETE /api/v1/documents/{document_id}/shares/{share_id}              — revoke grant

  Activity & Intelligence:
    GET    /api/v1/documents/{document_id}/activity                       — activity timeline
    POST   /api/v1/documents/{document_id}/ai/summary                     — AI summary
    POST   /api/v1/documents/{document_id}/ai/chat                        — document-scoped AI chat

  OCR & Extraction:
    POST   /api/v1/documents/{document_id}/ocr                            — trigger OCR
    GET    /api/v1/documents/{document_id}/text                           — get extracted text
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.middleware.rate_limit import RateLimiter
from app.models.document import (
    DocumentConfidentiality,
    DocumentLifecycleStatus,
    DocumentStatus,
)
from app.models.user import User
from app.schemas.document import (
    BulkDocumentIdsRequest,
    BulkOperationResponse,
    BulkShareRequest,
    BulkTagRequest,
    DocumentActivityResponse,
    DocumentAIChatRequest,
    DocumentAIChatResponse,
    DocumentAISummaryResponse,
    DocumentCreate,
    DocumentShareCreate,
    DocumentShareUpdate,
    DocumentUpdate,
    PaginatedDocumentResponse,
)
from app.services.document_ai_service import DocumentAIService
from app.services.document_service import DocumentService
from app.services.ocr_service import OCRService

router = APIRouter(
    prefix="/documents",
    tags=["Documents & Intelligence"],
)

_VALID_SORT_FIELDS = frozenset(
    {
        "created_at",
        "-created_at",
        "updated_at",
        "-updated_at",
        "file_name",
        "-file_name",
        "title",
        "-title",
        "file_size",
        "-file_size",
    }
)


def _get_service(db: AsyncSession = Depends(get_db)) -> DocumentService:
    return DocumentService(db)


def _get_ai_service(db: AsyncSession = Depends(get_db)) -> DocumentAIService:
    return DocumentAIService(db)


def _get_ocr_service(db: AsyncSession = Depends(get_db)) -> OCRService:
    return OCRService(db)


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# =============================================================================
# 1. Upload Document (Multipart)
# =============================================================================


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            RateLimiter(
                max_requests=settings.RATE_LIMIT_DOCUMENT_UPLOAD,
                window_seconds=60,
                group="doc_upload",
            )
        )
    ],
    summary="Upload a document",
    description="Streams multipart file to storage, creates Document record & Version 1, triggers OCR.",
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Document file (PDF, DOCX, XLSX, PNG, JPG, JPEG)."),
    title: str | None = Form(default=None),
    description: str | None = Form(default=None),
    category: str | None = Form(default=None),
    document_type: str | None = Form(default=None),
    tags: list[str] | None = Form(default=None),
    department_id: uuid.UUID | None = Form(default=None),
    confidentiality: DocumentConfidentiality = Form(default=DocumentConfidentiality.INTERNAL),
    retention_period_days: int | None = Form(default=None),
    expires_at: datetime | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Upload a document file with version 1 registration."""
    doc = await svc.upload_document(
        file=file,
        actor=current_user,
        title=title,
        description=description,
        category=category,
        document_type=document_type,
        tags=tags,
        department_id=department_id,
        confidentiality=confidentiality,
        retention_period_days=retention_period_days,
        expires_at=expires_at,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document uploaded successfully.",
        "data": doc.model_dump(mode="json"),
    }


# =============================================================================
# 2. Bulk Operations (Declared BEFORE /{document_id})
# =============================================================================


@router.post(
    "/bulk/archive",
    status_code=status.HTTP_200_OK,
    summary="Bulk archive documents",
    response_model=BulkOperationResponse,
)
async def bulk_archive_documents(
    payload: BulkDocumentIdsRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> BulkOperationResponse:
    """Archive multiple documents with per-item RBAC verification."""
    return await svc.bulk_archive(
        payload.document_ids,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/bulk/restore",
    status_code=status.HTTP_200_OK,
    summary="Bulk restore documents",
    response_model=BulkOperationResponse,
)
async def bulk_restore_documents(
    payload: BulkDocumentIdsRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> BulkOperationResponse:
    """Restore multiple archived/deleted documents."""
    return await svc.bulk_restore(
        payload.document_ids,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/bulk/delete",
    status_code=status.HTTP_200_OK,
    summary="Bulk delete documents",
    response_model=BulkOperationResponse,
)
async def bulk_delete_documents(
    payload: BulkDocumentIdsRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> BulkOperationResponse:
    """Soft-delete multiple documents."""
    return await svc.bulk_delete(
        payload.document_ids,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/bulk/tag",
    status_code=status.HTTP_200_OK,
    summary="Bulk tag documents",
    response_model=BulkOperationResponse,
)
async def bulk_tag_documents(
    payload: BulkTagRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> BulkOperationResponse:
    """Add or replace tags across multiple documents."""
    return await svc.bulk_tag(
        payload.document_ids,
        tags=payload.tags,
        replace=payload.replace,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/bulk/share",
    status_code=status.HTTP_200_OK,
    summary="Bulk share documents",
    response_model=BulkOperationResponse,
)
async def bulk_share_documents(
    payload: BulkShareRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> BulkOperationResponse:
    """Share multiple documents with a specific user."""
    return await svc.bulk_share(
        payload.document_ids,
        target_user_id=payload.user_id,
        permission=payload.permission,
        expires_at=payload.expires_at,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )


# =============================================================================
# 3. Document Listings & Creation
# =============================================================================


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List documents",
    response_model=PaginatedDocumentResponse,
)
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    lifecycle_status: DocumentLifecycleStatus | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    owner_id: uuid.UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    confidentiality: DocumentConfidentiality | None = Query(default=None),
    tag: str | None = Query(default=None),
    shared_with_me: bool = Query(default=False),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort: str | None = Query(default="-created_at"),
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> PaginatedDocumentResponse:
    """List documents with comprehensive enterprise filtering and RBAC."""
    if sort and sort not in _VALID_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort parameter '{sort}'. Allowed: {', '.join(sorted(_VALID_SORT_FIELDS))}",
        )

    return await svc.list_documents(
        actor=current_user,
        page=page,
        page_size=page_size,
        search=search,
        status_filter=status_filter,
        lifecycle_status=lifecycle_status,
        department_id=department_id,
        owner_id=owner_id,
        category=category,
        document_type=document_type,
        confidentiality=confidentiality,
        tag=tag,
        shared_with_me=shared_with_me,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create document metadata",
)
async def create_document(
    data: DocumentCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Create a document metadata record (backwards compatibility)."""
    doc = await svc.create_document(
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document created successfully.",
        "data": doc.model_dump(mode="json"),
    }


# =============================================================================
# 4. Single Document Operations
# =============================================================================


@router.get(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Get document metadata",
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Retrieve metadata for a single document."""
    doc = await svc.get_document(document_id, actor=current_user)
    return {
        "success": True,
        "message": "Document retrieved successfully.",
        "data": doc.model_dump(mode="json"),
    }


@router.patch(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Update document metadata",
)
async def update_document(
    document_id: uuid.UUID,
    data: DocumentUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Update allowed metadata fields."""
    doc = await svc.update_document(
        document_id,
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document updated successfully.",
        "data": doc.model_dump(mode="json"),
    }


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document",
)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Soft-delete a document."""
    await svc.delete_document(
        document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document deleted successfully.",
    }


# =============================================================================
# 5. Downloads & Previews
# =============================================================================


@router.get(
    "/{document_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download current document file",
)
async def download_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> StreamingResponse:
    """Stream the active document file binary."""
    stream, file_name, content_type, file_size = await svc.get_document_stream(
        document_id=document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{file_name}"',
    }
    if file_size > 0:
        headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers=headers,
    )


@router.get(
    "/{document_id}/preview",
    status_code=status.HTTP_200_OK,
    summary="Preview current document file inline",
)
async def preview_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> StreamingResponse:
    """Stream document binary inline for in-browser rendering."""
    stream, file_name, content_type, file_size = await svc.get_document_preview_stream(
        document_id=document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    headers: dict[str, str] = {
        "Content-Disposition": f'inline; filename="{file_name}"',
    }
    if file_size > 0:
        headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers=headers,
    )


# =============================================================================
# 6. Lifecycle Endpoints
# =============================================================================


@router.post(
    "/{document_id}/activate",
    status_code=status.HTTP_200_OK,
    summary="Activate document",
)
async def activate_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Transition document state to ACTIVE."""
    doc = await svc.activate_document(
        document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document activated successfully.",
        "data": doc.model_dump(mode="json"),
    }


@router.post(
    "/{document_id}/archive",
    status_code=status.HTTP_200_OK,
    summary="Archive document",
)
async def archive_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Transition document state to ARCHIVED."""
    doc = await svc.archive_document(
        document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document archived successfully.",
        "data": doc.model_dump(mode="json"),
    }


@router.post(
    "/{document_id}/restore",
    status_code=status.HTTP_200_OK,
    summary="Restore document to active state",
)
async def restore_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Restore document to ACTIVE."""
    doc = await svc.restore_document(
        document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document restored successfully.",
        "data": doc.model_dump(mode="json"),
    }


@router.post(
    "/{document_id}/expire",
    status_code=status.HTTP_200_OK,
    summary="Mark document as expired",
)
async def expire_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Transition document state to EXPIRED."""
    doc = await svc.expire_document(
        document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document expired successfully.",
        "data": doc.model_dump(mode="json"),
    }


# =============================================================================
# 7. Document Versions
# =============================================================================


@router.post(
    "/{document_id}/versions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            RateLimiter(
                max_requests=settings.RATE_LIMIT_DOCUMENT_UPLOAD,
                window_seconds=60,
                group="doc_version_upload",
            )
        )
    ],
    summary="Upload new document version",
)
async def upload_document_version(
    document_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(..., description="Replacement version file."),
    change_summary: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Upload a new version for an existing document."""
    version = await svc.create_new_version(
        document_id,
        file,
        actor=current_user,
        change_summary=change_summary,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "New document version created successfully.",
        "data": version.model_dump(mode="json"),
    }


@router.get(
    "/{document_id}/versions",
    status_code=status.HTTP_200_OK,
    summary="List document versions",
)
async def list_document_versions(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """List all versions for a document."""
    versions = await svc.list_versions(document_id, actor=current_user)
    return {
        "success": True,
        "message": "Document versions retrieved successfully.",
        "data": [v.model_dump(mode="json") for v in versions],
        "total_versions": len(versions),
    }


@router.get(
    "/{document_id}/versions/{version_id}",
    status_code=status.HTTP_200_OK,
    summary="Get version metadata",
)
async def get_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Get metadata for a specific document version."""
    version = await svc.get_version(document_id, version_id, actor=current_user)
    return {
        "success": True,
        "message": "Version retrieved successfully.",
        "data": version.model_dump(mode="json"),
    }


@router.post(
    "/{document_id}/versions/{version_id}/restore",
    status_code=status.HTTP_200_OK,
    summary="Restore a previous document version",
)
async def restore_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Restore a previous version by creating a new active version from it."""
    version = await svc.restore_version(
        document_id,
        version_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": f"Version {version.version_number} created from historical restore.",
        "data": version.model_dump(mode="json"),
    }


@router.get(
    "/{document_id}/versions/{version_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download specific document version",
)
async def download_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> StreamingResponse:
    """Stream download a specific version file binary."""
    stream, file_name, content_type, file_size = await svc.get_version_stream(
        document_id=document_id,
        version_id=version_id,
        actor=current_user,
    )
    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{file_name}"',
    }
    if file_size > 0:
        headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers=headers,
    )


# =============================================================================
# 8. Document Sharing & Access Grants
# =============================================================================


@router.post(
    "/{document_id}/shares",
    status_code=status.HTTP_201_CREATED,
    summary="Share document with user",
)
async def share_document(
    document_id: uuid.UUID,
    payload: DocumentShareCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Grant document access permissions to a user."""
    share = await svc.share_document(
        document_id,
        payload,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document shared successfully.",
        "data": share.model_dump(mode="json"),
    }


@router.get(
    "/{document_id}/shares",
    status_code=status.HTTP_200_OK,
    summary="List document access grants",
)
async def list_document_shares(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """List all active shares for a document."""
    shares = await svc.list_shares(document_id, actor=current_user)
    return {
        "success": True,
        "message": "Shares retrieved successfully.",
        "data": [s.model_dump(mode="json") for s in shares],
    }


@router.patch(
    "/{document_id}/shares/{share_id}",
    status_code=status.HTTP_200_OK,
    summary="Update document share",
)
async def update_document_share(
    document_id: uuid.UUID,
    share_id: uuid.UUID,
    payload: DocumentShareUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Update permissions or expiration on a share grant."""
    share = await svc.update_share(
        document_id,
        share_id,
        payload,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Share updated successfully.",
        "data": share.model_dump(mode="json"),
    }


@router.delete(
    "/{document_id}/shares/{share_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke document share",
)
async def revoke_document_share(
    document_id: uuid.UUID,
    share_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Revoke a document access grant."""
    await svc.revoke_share(
        document_id,
        share_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Access grant revoked successfully.",
    }


# =============================================================================
# 9. Activity Timeline
# =============================================================================


@router.get(
    "/{document_id}/activity",
    status_code=status.HTTP_200_OK,
    summary="Get document activity timeline",
    response_model=DocumentActivityResponse,
)
async def get_document_activity(
    document_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> DocumentActivityResponse:
    """Retrieve sanitized chronological audit events for a document."""
    return await svc.get_document_activity(
        document_id,
        actor=current_user,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# 10. Document AI Intelligence
# =============================================================================


@router.post(
    "/{document_id}/ai/summary",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(
            RateLimiter(
                max_requests=settings.RATE_LIMIT_AI_CHAT, window_seconds=60, group="doc_ai_summary"
            )
        )
    ],
    summary="Generate AI summary of document",
    response_model=DocumentAISummaryResponse,
)
async def generate_document_summary(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    ai_svc: DocumentAIService = Depends(_get_ai_service),
) -> DocumentAISummaryResponse:
    """Generate an AI executive summary for a document."""
    return await ai_svc.generate_summary(
        document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/{document_id}/ai/chat",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(
            RateLimiter(
                max_requests=settings.RATE_LIMIT_AI_CHAT, window_seconds=60, group="doc_ai_chat"
            )
        )
    ],
    summary="Document-scoped AI Q&A",
    response_model=DocumentAIChatResponse,
)
async def document_ai_chat(
    document_id: uuid.UUID,
    payload: DocumentAIChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    ai_svc: DocumentAIService = Depends(_get_ai_service),
) -> DocumentAIChatResponse:
    """Chat conversational Q&A strictly scoped to a single document."""
    return await ai_svc.document_chat(
        document_id,
        payload,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )


# =============================================================================
# 11. OCR & Text Extraction (Milestone 6)
# =============================================================================


@router.post(
    "/{document_id}/ocr",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger asynchronous OCR",
)
async def trigger_document_ocr(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    ocr_svc: OCRService = Depends(_get_ocr_service),
) -> dict[str, Any]:
    """Trigger background OCR processing for a document."""
    job_id, job_status = await ocr_svc.start_ocr_job(
        document_id=document_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "OCR job enqueued successfully.",
        "data": {
            "job_id": job_id,
            "document_id": str(document_id),
            "status": job_status,
        },
    }


@router.get(
    "/{document_id}/text",
    status_code=status.HTTP_200_OK,
    summary="Get extracted text and chunks",
)
async def get_document_text(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    ocr_svc: OCRService = Depends(_get_ocr_service),
) -> dict[str, Any]:
    """Retrieve full extracted text and chunk breakdown."""
    text_data = await ocr_svc.get_document_text(
        document_id=document_id,
        actor=current_user,
    )
    return {
        "success": True,
        "message": "Extracted text retrieved successfully.",
        "data": text_data.model_dump(mode="json"),
    }
