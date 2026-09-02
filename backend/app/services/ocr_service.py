"""
OCR and Text Extraction Service.

Orchestrates:
  - Triggering asynchronous Celery OCR extraction tasks
  - Polling Celery job statuses
  - Retrieving extracted document text and ordered chunks
  - Server-side RBAC and document ownership verification
  - Audit trail logging
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery.result import AsyncResult
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import OcrStatus
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.ocr import DocumentChunkResponse, DocumentTextResponse
from app.workers.celery_app import celery_app
from app.workers.ocr_tasks import process_document_ocr

logger = logging.getLogger(__name__)

_ADMIN_ROLES = frozenset({"admin", "hr"})


class OCRService:
    """Business logic for OCR triggering, status checking, and text extraction retrieval."""

    def __init__(self, db: AsyncSession) -> None:
        self._session = db
        self._doc_repo = DocumentRepository(db)
        self._chunk_repo = DocumentChunkRepository(db)
        self._audit_repo = AuditLogRepository(db)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _check_access(self, doc_owner_id: uuid.UUID, actor: User) -> None:
        """Enforce document ownership or administrative privileges."""
        role_name = (
            actor.role.name.lower()
            if actor.role and hasattr(actor.role, "name") and actor.role.name
            else str(getattr(actor, "role", "employee")).lower()
        )
        if role_name in _ADMIN_ROLES:
            return
        if doc_owner_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not own this document.",
            )

    # =========================================================================
    # 1. Trigger OCR Job
    # =========================================================================

    async def start_ocr_job(
        self,
        document_id: uuid.UUID,
        actor: User,
        ip_address: str | None = None,
    ) -> tuple[str, str]:
        """
        Validate permissions, set document ocr_status to 'processing', and enqueue Celery task.

        Returns:
            Tuple of (job_id, status_string).
        """
        doc = await self._doc_repo.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        self._check_access(doc.owner_id, actor)

        # Set status to processing
        doc.ocr_status = OcrStatus.PROCESSING

        # Audit log
        await self._audit_repo.create(
            action="document.ocr_start",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            ip_address=ip_address,
            new_value={"ocr_status": "processing"},
        )

        await self._session.commit()

        # Enqueue Celery task
        task = process_document_ocr.delay(str(document_id))
        logger.info("Enqueued OCR Celery task %s for document %s", task.id, document_id)

        return task.id, "PROCESSING"

    # =========================================================================
    # 2. Get Job Status
    # =========================================================================

    async def get_ocr_job_status(
        self,
        job_id: str,
        actor: User,
    ) -> dict[str, Any]:
        """
        Query Celery result backend for task state and map to standardized API response.

        States:
          PENDING     -> PENDING
          STARTED     -> PROCESSING
          PROGRESS    -> PROCESSING
          SUCCESS     -> COMPLETED
          FAILURE     -> FAILED
          RETRY       -> PROCESSING
          REVOKED     -> FAILED
        """
        result = AsyncResult(job_id, app=celery_app)
        celery_state = result.state

        state_map = {
            "PENDING": "PENDING",
            "STARTED": "PROCESSING",
            "PROGRESS": "PROCESSING",
            "SUCCESS": "COMPLETED",
            "FAILURE": "FAILED",
            "RETRY": "PROCESSING",
            "REVOKED": "FAILED",
        }

        api_status = state_map.get(celery_state, "PENDING")
        safe_result: dict[str, Any] | None = None

        if celery_state == "SUCCESS":
            if isinstance(result.result, dict):
                safe_result = {
                    "document_id": result.result.get("document_id"),
                    "file_name": result.result.get("file_name"),
                    "total_chunks": result.result.get("total_chunks"),
                    "char_count": result.result.get("char_count"),
                }
        elif celery_state == "FAILURE":
            safe_result = {
                "error": "OCR processing failed during extraction or chunking.",
            }

        return {
            "job_id": job_id,
            "status": api_status,
            "result": safe_result,
        }

    # =========================================================================
    # 3. Retrieve Extracted Text & Chunks
    # =========================================================================

    async def get_document_text(
        self,
        document_id: uuid.UUID,
        actor: User,
    ) -> DocumentTextResponse:
        """Retrieve aggregated extracted text and chunk breakdown for a document."""
        doc = await self._doc_repo.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        self._check_access(doc.owner_id, actor)

        chunk_models = await self._chunk_repo.get_chunks_by_document(document_id)
        chunk_responses = [
            DocumentChunkResponse(
                id=c.id,
                chunk_number=c.chunk_number,
                content=c.content,
                created_at=c.created_at,
            )
            for c in chunk_models
        ]

        full_text = "\n\n".join(c.content for c in chunk_models)

        return DocumentTextResponse(
            document_id=doc.id,
            file_name=doc.file_name,
            ocr_status=doc.ocr_status.value
            if hasattr(doc.ocr_status, "value")
            else str(doc.ocr_status),
            total_chunks=len(chunk_responses),
            text=full_text,
            chunks=chunk_responses,
        )
