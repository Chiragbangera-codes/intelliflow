"""
Celery background task for asynchronous document OCR and text extraction.

Task:
  tasks.process_document_ocr(document_id: str)

Workflow:
  1. Open async database session.
  2. Retrieve Document record.
  3. Validate physical storage file.
  4. Extract text using ExtractorService.
  5. Chunk text into ordered DocumentChunk records.
  6. Atomic overwrite in document_chunks table.
  7. Transition ocr_status to 'completed'.
  8. Create audit entry 'document.ocr_complete'.
  9. On failure: transition ocr_status to 'failed', log audit 'document.ocr_failed', re-raise.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.document import DocumentStatus, OcrStatus
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.extractor_service import ExtractorService
from app.services.storage_service import StorageService
from app.workers.celery_app import celery_app
from app.workers.task_runner import run_in_worker

logger = logging.getLogger(__name__)


# Imported lazily below to avoid circular imports at module load time.
# The embedding task is dispatched after OCR completes.
_EMBED_TASK_NAME = "tasks.embed_document_chunks"


async def _async_process_document_ocr(
    document_id_str: str,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Execute asynchronous document text extraction and chunk persistence."""
    document_id = uuid.UUID(document_id_str)

    async def _run(session: AsyncSession) -> dict[str, Any]:
        doc_repo = DocumentRepository(session)
        chunk_repo = DocumentChunkRepository(session)
        audit_repo = AuditLogRepository(session)
        storage_svc = StorageService()
        extractor_svc = ExtractorService()

        # 1. Fetch document
        doc = await doc_repo.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            logger.error("OCR task: Document %s not found or deleted.", document_id)
            raise ValueError(f"Document {document_id} not found or has been deleted.")

        logger.info(
            "OCR task: Starting text extraction for document %s (%s)", doc.id, doc.file_name
        )

        try:
            # 2. Resolve safe physical path (local or downloaded from Supabase Storage)
            async with storage_svc.scoped_local_path(doc.storage_path) as file_path:
                # 3. Extract text
                extracted_text = extractor_svc.extract_text(
                    file_path=file_path,
                    file_name=doc.file_name,
                    file_type=doc.file_type,
                )

            # 4. Chunk text
            chunks = extractor_svc.chunk_text(extracted_text)

            # 5. Persist chunks
            await chunk_repo.save_chunks(document_id=doc.id, chunks=chunks)

            # 6. Update document status
            doc.ocr_status = OcrStatus.COMPLETED
            if doc.status == DocumentStatus.PENDING or doc.status == DocumentStatus.PROCESSING:
                doc.status = DocumentStatus.PROCESSED

            # 7. Audit log
            await audit_repo.create(
                action="document.ocr_complete",
                user_id=doc.owner_id,
                table_name="documents",
                record_id=doc.id,
                new_value={
                    "total_chunks": len(chunks),
                    "char_count": len(extracted_text),
                    "ocr_status": "completed",
                },
            )

            await session.commit()
            logger.info(
                "OCR task: Successfully completed for document %s. Chunks created: %d",
                doc.id,
                len(chunks),
            )

            # Dispatch embedding task asynchronously.
            # This is fire-and-forget: a dispatch failure must NOT fail the OCR task.
            try:
                celery_app.send_task(_EMBED_TASK_NAME, args=[document_id_str])
                logger.info(
                    "OCR task: Dispatched embedding task for document %s.",
                    doc.id,
                )
            except Exception as dispatch_exc:
                logger.error(
                    "OCR task: Failed to dispatch embedding task for document %s: %s. "
                    "OCR result is still valid — embedding can be retried manually.",
                    doc.id,
                    dispatch_exc,
                )

            return {
                "document_id": str(doc.id),
                "file_name": doc.file_name,
                "status": "completed",
                "total_chunks": len(chunks),
                "char_count": len(extracted_text),
            }

        except Exception as exc:
            logger.exception("OCR task failed for document %s: %s", doc.id, exc)
            await session.rollback()

            # Record failure status and audit log in fresh transaction
            try:
                failed_doc = await doc_repo.get_by_id(document_id)
                if failed_doc:
                    failed_doc.ocr_status = OcrStatus.FAILED
                    await audit_repo.create(
                        action="document.ocr_failed",
                        user_id=failed_doc.owner_id,
                        table_name="documents",
                        record_id=failed_doc.id,
                        new_value={
                            "error": str(exc),
                            "ocr_status": "failed",
                        },
                    )
                    await session.commit()
            except Exception as fail_err:
                logger.error(
                    "Failed to commit failure status for doc %s: %s", document_id, fail_err
                )

            raise exc

    if db is not None:
        return await _run(db)

    async with AsyncSessionLocal() as session:
        return await _run(session)


@celery_app.task(
    name="tasks.process_document_ocr",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
)
def process_document_ocr(self: Any, document_id: str) -> dict[str, Any]:
    """
    Celery task entrypoint for document OCR and text extraction.

    Args:
        document_id: String UUID of the document to process.

    Returns:
        Summary dict containing document_id, status, total_chunks.
    """
    logger.info("Executing Celery OCR task %s for document_id=%s", self.request.id, document_id)
    return run_in_worker(_async_process_document_ocr(document_id))
