"""
Document management API routes.

Provides endpoints for:
  - POST   /api/v1/documents/upload          — multipart streaming file upload (Milestone 5)
  - GET    /api/v1/documents/{id}/download   — streaming file download (Milestone 5)
  - GET    /api/v1/documents                 — list with search, filter, sort, pagination
  - GET    /api/v1/documents/{id}            — get metadata
  - POST   /api/v1/documents                 — create metadata
  - PATCH  /api/v1/documents/{id}            — update metadata
  - DELETE /api/v1/documents/{id}            — soft-delete

Security:
  - owner_id is always stamped from the authenticated JWT session.
  - Non-admin users can access only their own documents.
  - status / ocr_status are server-controlled.
  - Streaming uploads prevent RAM exhaustion; file paths are verified against traversal.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.document import DocumentStatus
from app.models.user import User
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.document_service import DocumentService
from app.services.ocr_service import OCRService

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

_VALID_SORT_FIELDS = frozenset(
    {"created_at", "-created_at", "file_name", "-file_name", "file_size", "-file_size"}
)


def _get_service(db: AsyncSession = Depends(get_db)) -> DocumentService:
    """Provide a DocumentService instance with the injected DB session."""
    return DocumentService(db)


def _get_ocr_service(db: AsyncSession = Depends(get_db)) -> OCRService:
    """Provide an OCRService instance with the injected DB session."""
    return OCRService(db)


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# =============================================================================
# POST /documents/upload — multipart file upload (Milestone 5)
# =============================================================================


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "Streams a multipart file to secure local storage, calculates its SHA-256 checksum, "
        "validates format and size (max 100 MB), stamps owner_id from the authenticated user, "
        "and logs the operation."
    ),
    responses={
        201: {"description": "Document uploaded and metadata registered successfully."},
        400: {"description": "Invalid file format or name."},
        401: {"description": "Not authenticated."},
        413: {"description": "File exceeds 100 MB size limit."},
        500: {"description": "Storage or database failure."},
    },
)
async def upload_document(
    request: Request,
    file: UploadFile = File(
        ..., description="Document file to upload (PDF, DOCX, XLSX, PNG, JPG, JPEG)."
    ),
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Upload a document with streaming storage and SHA-256 calculation."""
    doc = await svc.upload_document(
        file=file,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Document uploaded successfully.",
        "data": doc.model_dump(mode="json"),
    }


# =============================================================================
# GET /documents/{document_id}/download — file download (Milestone 5)
# =============================================================================


@router.get(
    "/{document_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download document file",
    description=(
        "Streams the physical file binary with Content-Disposition headers. "
        "Requires authentication. Non-admin users may only download their own documents."
    ),
    responses={
        200: {"description": "File stream."},
        401: {"description": "Not authenticated."},
        403: {"description": "Access denied."},
        404: {"description": "Document or physical file not found."},
    },
)
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> FileResponse:
    """Stream the physical file to the client."""
    file_path, file_name, content_type, file_size = await svc.get_document_file_path(
        document_id=document_id,
        actor=current_user,
    )
    return FileResponse(
        path=file_path,
        filename=file_name,
        media_type=content_type,
        headers={"Content-Length": str(file_size)},
    )


# =============================================================================
# GET /documents — list (with search, status filter, sort, pagination)
# =============================================================================


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List documents",
    description=(
        "Returns a paginated list of document metadata. "
        "Supports search by filename, status filtering, and sorting. "
        "admin/hr see all documents; other roles see only their own."
    ),
    responses={
        200: {"description": "Documents retrieved successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page."),
    search: str | None = Query(default=None, description="Case-insensitive filename search."),
    status_filter: DocumentStatus | None = Query(
        default=None,
        alias="status",
        description="Filter by document status (pending, processing, processed, failed).",
    ),
    sort: str | None = Query(
        default="-created_at",
        description="Sort by created_at, -created_at, file_name, -file_name, file_size, -file_size.",
    ),
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """List documents with search, filter, sort, and pagination."""
    if sort and sort not in _VALID_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort parameter '{sort}'. Allowed values: {', '.join(sorted(_VALID_SORT_FIELDS))}",
        )

    result = await svc.list_documents(
        actor=current_user,
        page=page,
        page_size=page_size,
        search=search,
        status_filter=status_filter,
        sort=sort,
    )
    return {
        "success": True,
        "message": result.message,
        "data": [d.model_dump(mode="json") for d in result.data],
        "meta": result.meta,
    }


# =============================================================================
# GET /documents/{document_id} — get metadata
# =============================================================================


@router.get(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a document by ID",
    description=(
        "Returns metadata for a single document. "
        "Returns 403 if the caller does not own the document (unless admin/hr)."
    ),
    responses={
        200: {"description": "Document retrieved successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Access denied."},
        404: {"description": "Document not found."},
    },
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Return metadata for a single document."""
    doc = await svc.get_document(document_id, actor=current_user)
    return {
        "success": True,
        "message": "Document retrieved successfully.",
        "data": doc.model_dump(mode="json"),
    }


# =============================================================================
# POST /documents — create metadata (backwards compatibility)
# =============================================================================


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a document metadata record",
    description=(
        "Creates a document metadata record. "
        "The owner is always the authenticated user — never from the request body. "
        "status and ocr_status are initialised to 'pending' by the server."
    ),
    responses={
        201: {"description": "Document created successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def create_document(
    data: DocumentCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Create a document metadata record owned by the authenticated user."""
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
# PATCH /documents/{document_id} — update metadata
# =============================================================================


@router.patch(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Update document metadata",
    description=(
        "Partially updates allowed metadata fields: file_name, file_type, checksum. "
        "status, ocr_status, storage_path, and owner_id are immutable. "
        "Returns 403 if the caller does not own the document (unless admin/hr)."
    ),
    responses={
        200: {"description": "Document updated successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Access denied."},
        404: {"description": "Document not found."},
    },
)
async def update_document(
    document_id: uuid.UUID,
    data: DocumentUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Update allowed metadata fields for a document."""
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


# =============================================================================
# DELETE /documents/{document_id} — soft-delete
# =============================================================================


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document",
    description=(
        "Soft-deletes a document record and creates an audit trail entry. "
        "Returns 403 if the caller does not own the document (unless admin/hr)."
    ),
    responses={
        200: {"description": "Document deleted successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Access denied."},
        404: {"description": "Document not found."},
    },
)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: DocumentService = Depends(_get_service),
) -> dict[str, Any]:
    """Soft-delete a document — checks ownership in service."""
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
# POST /documents/{document_id}/ocr — trigger OCR task (Milestone 6)
# =============================================================================


@router.post(
    "/{document_id}/ocr",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger asynchronous OCR and text extraction",
    description=(
        "Enqueues a Celery background job to extract text from the document, "
        "chunk the text, persist chunks, and update OCR status."
    ),
    responses={
        202: {"description": "OCR job enqueued."},
        401: {"description": "Not authenticated."},
        403: {"description": "Access denied."},
        404: {"description": "Document not found."},
    },
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


# =============================================================================
# GET /documents/{document_id}/text — retrieve extracted text & chunks (Milestone 6)
# =============================================================================


@router.get(
    "/{document_id}/text",
    status_code=status.HTTP_200_OK,
    summary="Get extracted document text and chunks",
    description="Returns full reconstructed text along with ordered chunks for a document.",
    responses={
        200: {"description": "Extracted text and chunks."},
        401: {"description": "Not authenticated."},
        403: {"description": "Access denied."},
        404: {"description": "Document not found."},
    },
)
async def get_document_text(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    ocr_svc: OCRService = Depends(_get_ocr_service),
) -> dict[str, Any]:
    """Retrieve full extracted text and chunk breakdown for a document."""
    text_data = await ocr_svc.get_document_text(
        document_id=document_id,
        actor=current_user,
    )
    return {
        "success": True,
        "message": "Extracted text retrieved successfully.",
        "data": text_data.model_dump(mode="json"),
    }
