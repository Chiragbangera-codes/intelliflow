"""
Admin AI API — index administration (admin-only).

Endpoints:
  POST /api/v1/admin/ai/reindex        — dispatch a full embedding/FAISS rebuild
  GET  /api/v1/admin/ai/index-status   — report chunk/embedding/FAISS consistency
  GET  /api/v1/admin/ai/health         — comprehensive AI subsystem health & observability

Security:
  Every route is gated by require_role("admin"). Employees, managers, and HR
  receive 403. Unauthenticated requests receive 401 (from get_current_user).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.ai_embedding import AIEmbedding
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.schemas.admin import (
    AIHealthData,
    AIHealthResponse,
    AIIndexStatusData,
    AIIndexStatusResponse,
    ReindexAcceptedData,
    ReindexResponse,
)
from app.services.vector_store_service import vector_store
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

_REINDEX_TASK_NAME = "tasks.reindex_all_embeddings"


@router.post(
    "/ai/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReindexResponse,
    summary="Rebuild all embeddings and the FAISS index (admin only)",
    description=(
        "Dispatch a background job that re-embeds every chunk of every "
        "non-deleted document and rebuilds the FAISS index from PostgreSQL. "
        "Idempotent. Admin only. Returns 202 with the Celery task id."
    ),
)
async def reindex_ai_index(
    _current_user: User = Depends(require_role("admin")),
) -> ReindexResponse:
    """Dispatch the reindex Celery task to the worker."""
    try:
        result = celery_app.send_task(_REINDEX_TASK_NAME)
    except Exception:
        # Broker unreachable, etc. Do not leak internals.
        logger.exception("Failed to dispatch reindex task.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to dispatch the reindex job. Please try again shortly.",
        ) from None

    logger.info("Admin %s dispatched reindex task %s", _current_user.id, result.id)
    return ReindexResponse(
        data=ReindexAcceptedData(task_id=str(result.id), status="accepted"),
    )


@router.get(
    "/ai/index-status",
    status_code=status.HTTP_200_OK,
    response_model=AIIndexStatusResponse,
    summary="Report embedding/FAISS consistency (admin only)",
    description=(
        "Return counts of chunks, embeddings, and FAISS vectors plus a "
        "consistency flag. "
        "Useful to detect the 'chunks without embeddings' gap before or after "
        "a reindex. Admin only."
    ),
)
async def ai_index_status(
    _current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AIIndexStatusResponse:
    """Compute chunk/embedding/FAISS counts for non-deleted documents."""
    chunks_stmt = (
        select(func.count(DocumentChunk.id))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.deleted_at.is_(None))
    )
    embeddings_stmt = (
        select(func.count(AIEmbedding.id))
        .join(DocumentChunk, DocumentChunk.id == AIEmbedding.document_chunk_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.deleted_at.is_(None))
    )
    missing_stmt = (
        select(func.count(DocumentChunk.id))
        .join(Document, Document.id == DocumentChunk.document_id)
        .outerjoin(AIEmbedding, AIEmbedding.document_chunk_id == DocumentChunk.id)
        .where(Document.deleted_at.is_(None), AIEmbedding.id.is_(None))
    )

    chunks = int((await db.execute(chunks_stmt)).scalar_one())
    embeddings = int((await db.execute(embeddings_stmt)).scalar_one())
    missing = int((await db.execute(missing_stmt)).scalar_one())

    vector_store.ensure_loaded()
    faiss_vectors = vector_store.vector_count

    consistent = missing == 0 and chunks == embeddings == faiss_vectors

    return AIIndexStatusResponse(
        data=AIIndexStatusData(
            chunks=chunks,
            embeddings=embeddings,
            faiss_vectors=faiss_vectors,
            missing_embeddings=missing,
            consistent=consistent,
        ),
    )


@router.get(
    "/ai/health",
    status_code=status.HTTP_200_OK,
    response_model=AIHealthResponse,
    summary="Comprehensive AI subsystem health check & observability (admin only)",
    description=(
        "Return an observability health snapshot: whether FAISS is loaded, "
        "vector count, consistency flag, model info, and retrieval configuration. "
        "Never exposes document contents or user data. Admin only."
    ),
)
async def ai_health(
    _current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AIHealthResponse:
    """Provide a comprehensive AI health and observability check for monitoring."""
    chunks_stmt = (
        select(func.count(DocumentChunk.id))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.deleted_at.is_(None))
    )
    missing_stmt = (
        select(func.count(DocumentChunk.id))
        .join(Document, Document.id == DocumentChunk.document_id)
        .outerjoin(AIEmbedding, AIEmbedding.document_chunk_id == DocumentChunk.id)
        .where(Document.deleted_at.is_(None), AIEmbedding.id.is_(None))
    )
    docs_with_chunks_stmt = (
        select(func.count(func.distinct(DocumentChunk.document_id)))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.deleted_at.is_(None))
    )

    chunks = int((await db.execute(chunks_stmt)).scalar_one())
    missing = int((await db.execute(missing_stmt)).scalar_one())
    docs_with_chunks = int((await db.execute(docs_with_chunks_stmt)).scalar_one())

    vector_store.ensure_loaded()
    faiss_vectors = vector_store.vector_count
    faiss_loaded = vector_store.is_loaded

    consistent = missing == 0 and chunks == faiss_vectors

    if not faiss_loaded:
        health_status = "unavailable"
    elif missing > 0 or not consistent:
        health_status = "degraded"
    else:
        health_status = "healthy"

    index_path = Path(settings.FAISS_INDEX_PATH)
    last_index_mtime: float | None = None
    try:
        last_index_mtime = index_path.stat().st_mtime
    except OSError:
        pass

    return AIHealthResponse(
        data=AIHealthData(
            status=health_status,
            faiss_loaded=faiss_loaded,
            faiss_vectors=faiss_vectors,
            consistent=consistent,
            missing_embeddings=missing,
            documents_with_chunks=docs_with_chunks,
            embedding_model=settings.EMBEDDING_MODEL,
            vector_dimension=384,
            reranker_enabled=settings.AI_RERANK_ENABLED,
            hybrid_enabled=settings.AI_HYBRID_ENABLED,
            rrf_k=settings.AI_RRF_K,
            last_index_mtime=last_index_mtime,
            semantic_multiplier=settings.AI_SEMANTIC_CANDIDATE_MULTIPLIER,
            max_candidates=settings.AI_MAX_RETRIEVAL_CANDIDATES,
            lexical_candidates=settings.AI_LEXICAL_CANDIDATES,
        ),
    )
