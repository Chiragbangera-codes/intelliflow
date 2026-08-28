"""
Celery background tasks for AI embedding pipeline (Milestone 7 — Phase 1).

Task:
    tasks.embed_document_chunks(document_id: str)

Workflow:
    1. Load DocumentChunk rows for the document from PostgreSQL.
    2. If no chunks exist, log and return gracefully (OCR may not have run yet).
    3. Batch-embed all chunk contents using EmbeddingService.
    4. Persist AIEmbedding metadata rows (create or replace per chunk).
    5. Add vectors to the FAISS index (VectorStoreService).
    6. Save FAISS index to disk.
    7. Create audit log entry: document.embeddings_complete.
    8. Return structured result dict.

Failure handling:
    - Embedding failures are logged and re-raised so Celery marks the task as FAILED.
    - A failed embedding task does NOT affect the document's OCR status.
    - Partial DB state is rolled back on exception.

Design constraints:
    - OCR pipeline must remain functional even if embedding is unavailable.
    - FAISS index is only written after all DB operations succeed.
    - Document text content is never stored inside FAISS.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.repositories.ai_embedding_repository import AIEmbeddingRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import embedding_service
from app.services.reindex_service import reindex_all_embeddings
from app.services.vector_store_service import ChunkVector, vector_store
from app.workers.celery_app import celery_app
from app.workers.task_runner import run_in_worker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async implementation
# ---------------------------------------------------------------------------


async def _async_embed_document_chunks(
    document_id_str: str,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """
    Core async logic for the embedding Celery task.

    Separated from the Celery entry-point so it can be called directly in
    tests with an injected database session.
    """
    document_id = uuid.UUID(document_id_str)

    async def _run(session: AsyncSession) -> dict[str, Any]:
        doc_repo = DocumentRepository(session)
        chunk_repo = DocumentChunkRepository(session)
        embedding_repo = AIEmbeddingRepository(session)
        audit_repo = AuditLogRepository(session)

        # 1. Validate document still exists
        doc = await doc_repo.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            logger.error(
                "Embedding task: Document %s not found or deleted — aborting.",
                document_id,
            )
            return {
                "document_id": document_id_str,
                "chunks_processed": 0,
                "status": "skipped",
                "reason": "document_not_found",
            }

        # 2. Load chunks
        chunks = await chunk_repo.get_chunks_by_document(document_id)
        if not chunks:
            logger.info(
                "Embedding task: No chunks found for document %s — "
                "OCR may not have completed yet. Skipping.",
                document_id,
            )
            return {
                "document_id": document_id_str,
                "chunks_processed": 0,
                "status": "skipped",
                "reason": "no_chunks",
            }

        logger.info(
            "Embedding task: Embedding %d chunks for document %s (%s).",
            len(chunks),
            document_id,
            doc.file_name,
        )

        try:
            # 3. Batch embed all chunk texts
            texts = [chunk.content for chunk in chunks]
            vectors = embedding_service.embed_batch(texts)

            # 4. Persist AIEmbedding metadata rows
            #    Delete existing embeddings for this document first (idempotent re-run).
            await embedding_repo.delete_by_document_id(document_id)

            chunk_vectors: list[ChunkVector] = []
            for chunk, vector in zip(chunks, vectors, strict=False):
                # Create or update AIEmbedding record.
                # vector_reference uses the chunk UUID as a stable identifier.
                # The actual FAISS row ID is implicit from insertion order.
                await embedding_repo.create(
                    document_chunk_id=chunk.id,
                    vector_reference=str(chunk.id),
                    embedding_model=settings.EMBEDDING_MODEL,
                )

                chunk_vectors.append(ChunkVector(chunk_id=chunk.id, vector=vector))

            await session.flush()

            # 5. Add to FAISS (after DB flush — don't write FAISS if DB fails)
            vector_store.add_chunks(chunk_vectors)

            # 6. Save FAISS index to disk
            vector_store.save()

            # 7. Audit log
            await audit_repo.create(
                action="document.embeddings_complete",
                user_id=doc.owner_id,
                table_name="documents",
                record_id=doc.id,
                new_value={
                    "chunks_embedded": len(chunks),
                    "embedding_model": "all-MiniLM-L6-v2",
                    "faiss_total": vector_store.vector_count,
                },
            )

            await session.commit()

            logger.info(
                "Embedding task: Completed for document %s. "
                "Chunks embedded: %d. FAISS total: %d.",
                document_id,
                len(chunks),
                vector_store.vector_count,
            )

            return {
                "document_id": document_id_str,
                "chunks_processed": len(chunks),
                "status": "completed",
                "faiss_total": vector_store.vector_count,
            }

        except Exception as exc:
            logger.exception(
                "Embedding task: Failed for document %s: %s",
                document_id,
                exc,
            )
            await session.rollback()
            raise

    if db is not None:
        return await _run(db)

    async with AsyncSessionLocal() as session:
        return await _run(session)


# ---------------------------------------------------------------------------
# Celery task entry-point
# ---------------------------------------------------------------------------


@celery_app.task(
    name="tasks.embed_document_chunks",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
)
def embed_document_chunks(self: Any, document_id: str) -> dict[str, Any]:
    """
    Celery task: embed document chunks and update the FAISS index.

    Dispatched automatically by the OCR task after successful text extraction.
    Can also be triggered manually for re-embedding.

    Self-healing: transient failures (e.g. a memory blip while loading the
    embedding model, a momentary DB hiccup) are retried automatically up to
    3 times with exponential backoff + jitter. Combined with the app's
    ``task_acks_late=True`` setting, a task whose worker is OOM-killed mid-run
    is redelivered and re-executed rather than silently lost — which is exactly
    the failure mode that previously left documents with chunks but no
    embeddings.

    Args:
        document_id: String UUID of the document to embed.

    Returns:
        Result dict with document_id, chunks_processed, status.
    """
    logger.info(
        "Executing Celery embedding task %s for document_id=%s",
        self.request.id,
        document_id,
    )
    return run_in_worker(_async_embed_document_chunks(document_id))


# ---------------------------------------------------------------------------
# Reindex task — full FAISS/embedding rebuild (admin-triggered)
# ---------------------------------------------------------------------------


async def _async_reindex_all() -> dict[str, Any]:
    """Open a session and delegate to the shared reindex service."""
    async with AsyncSessionLocal() as session:
        return await reindex_all_embeddings(session)


@celery_app.task(name="tasks.reindex_all_embeddings", bind=True)
def reindex_all_embeddings_task(self: Any) -> dict[str, Any]:
    """
    Celery task: rebuild ALL embeddings + the FAISS index from PostgreSQL.

    Dispatched by the admin-only ``POST /api/v1/admin/ai/reindex`` endpoint.
    Runs in the worker (where the embedding model and CPU/memory budget live),
    not the API process. After it saves the rebuilt index, the API process
    picks up the change automatically via VectorStoreService's mtime check —
    no restart required.

    Not auto-retried: it is a heavy, admin-initiated operation and a partial
    retry storm would be worse than a clean re-invocation. Failures are logged
    and surfaced in the task result.

    Returns:
        The reconciliation report dict (counts + per-document breakdown).
    """
    logger.info("Executing Celery reindex task %s", self.request.id)
    return run_in_worker(_async_reindex_all())
