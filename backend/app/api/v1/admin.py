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
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.ai_embedding import AIEmbedding
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_execution import WorkflowExecution
from app.schemas.admin import (
    AIHealthData,
    AIHealthResponse,
    AIIndexStatusData,
    AIIndexStatusResponse,
    ReindexAcceptedData,
    ReindexResponse,
    SystemMetricsData,
    SystemMetricsResponse,
)
from app.schemas.security import SecurityEventListResponse, SecuritySummaryResponse
from app.services.health_service import HealthService
from app.services.security_audit_service import SecurityAuditService
from app.services.vector_store_service import vector_store
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


def _get_security_service(db: AsyncSession = Depends(get_db)) -> SecurityAuditService:
    return SecurityAuditService(db)


def _get_health_service() -> HealthService:
    return HealthService()


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


# =============================================================================
# Milestone 12 — Security Auditing & System Observability
# =============================================================================


@router.get(
    "/security/events",
    status_code=status.HTTP_200_OK,
    response_model=SecurityEventListResponse,
    summary="List & filter security events (Admin only)",
    description=(
        "Retrieve sanitized security and audit events with multi-dimensional filtering "
        "(action, severity, user, status, date range) and pagination. Admin only."
    ),
)
async def list_security_events(
    _current_user: User = Depends(require_role("admin")),
    action: str | None = Query(None, description="Action filter (e.g. 'auth.login_failed')"),
    user_id: uuid.UUID | None = Query(None, description="User UUID filter"),
    severity: str | None = Query(None, description="Severity: info, warning, critical"),
    status: str | None = Query(None, description="Status: success, failure"),
    start_date: datetime | None = Query(None, description="ISO start date filter"),
    end_date: datetime | None = Query(None, description="ISO end date filter"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sec_svc: SecurityAuditService = Depends(_get_security_service),
) -> SecurityEventListResponse:
    """Retrieve filtered and paginated security events."""
    return await sec_svc.get_security_events(
        action=action,
        user_id=user_id,
        severity=severity,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/security/summary",
    status_code=status.HTTP_200_OK,
    response_model=SecuritySummaryResponse,
    summary="Get 24h security overview metrics (Admin only)",
    description="Calculates 24-hour summary of failed logins, rate limit violations, unauthorized attempts, and active sessions.",
)
async def get_security_summary(
    _current_user: User = Depends(require_role("admin")),
    sec_svc: SecurityAuditService = Depends(_get_security_service),
) -> SecuritySummaryResponse:
    """Retrieve 24h security metrics summary."""
    return await sec_svc.get_security_summary()


@router.get(
    "/system/metrics",
    status_code=status.HTTP_200_OK,
    response_model=SystemMetricsResponse,
    summary="Get system observability metrics (Admin only)",
    description="Provides real-time telemetry on backend, database, Redis, Celery, and entity counts.",
)
async def get_system_metrics(
    _current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    health_svc: HealthService = Depends(_get_health_service),
) -> SystemMetricsResponse:
    """Compute system-wide observability metrics."""
    diag = await health_svc.get_diagnostics(db)
    d = diag.data

    # Count core enterprise entities efficiently
    users_cnt = int((await db.execute(select(func.count(User.id)))).scalar_one())
    docs_cnt = int(
        (
            await db.execute(select(func.count(Document.id)).where(Document.deleted_at.is_(None)))
        ).scalar_one()
    )
    wf_cnt = int((await db.execute(select(func.count(Workflow.id)))).scalar_one())
    exec_cnt = int((await db.execute(select(func.count(WorkflowExecution.id)))).scalar_one())

    db_health = d.dependencies.get("database")
    redis_health = d.dependencies.get("redis")
    celery_health = d.dependencies.get("celery")
    ai_health = d.dependencies.get("faiss")

    metrics_data = SystemMetricsData(
        status=d.status,
        uptime_seconds=d.uptime_seconds,
        memory_usage_mb=d.memory_usage_mb,
        environment=d.environment,
        database_status=db_health.status if db_health else "unknown",
        database_latency_ms=db_health.latency_ms if db_health else None,
        redis_status=redis_health.status if redis_health else "unknown",
        redis_latency_ms=redis_health.latency_ms if redis_health else None,
        celery_status=celery_health.status if celery_health else "unknown",
        ai_status=ai_health.status if ai_health else "unknown",
        faiss_vectors=d.faiss_vectors,
        total_users_count=users_cnt,
        total_documents_count=docs_cnt,
        total_workflows_count=wf_cnt,
        total_executions_count=exec_cnt,
        timestamp=datetime.now(UTC),
    )

    return SystemMetricsResponse(success=True, data=metrics_data)
