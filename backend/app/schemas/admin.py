"""
Admin API schemas — AI index administration.

Follows the project-wide response convention:
    { "success": true, "message": "...", "data": { ... } }
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# =============================================================================
# POST /admin/ai/reindex
# =============================================================================


class ReindexAcceptedData(BaseModel):
    """Data payload returned when a reindex job is accepted for background run."""

    task_id: str = Field(description="Celery task id of the dispatched reindex job.")
    status: str = Field(
        default="accepted",
        description="Dispatch status. 'accepted' means the job was queued to the worker.",
    )


class ReindexResponse(BaseModel):
    """Envelope for POST /api/v1/admin/ai/reindex (HTTP 202)."""

    success: bool = True
    message: str = "Reindex job dispatched. It runs in the background on the worker."
    data: ReindexAcceptedData


# =============================================================================
# GET /admin/ai/index-status
# =============================================================================


class AIIndexStatusData(BaseModel):
    """
    Consistency snapshot of the embedding/FAISS pipeline.

    consistent is True iff every non-deleted chunk has exactly one embedding and
    the FAISS vector count matches the embedding count — i.e. the invariant the
    reindex operation restores currently holds.
    """

    chunks: int = Field(description="Total document_chunks for non-deleted documents.")
    embeddings: int = Field(description="Total ai_embeddings rows for those chunks.")
    faiss_vectors: int = Field(description="Vectors currently in the in-memory FAISS index.")
    missing_embeddings: int = Field(
        description="Chunks (non-deleted docs) that have no ai_embeddings row."
    )
    consistent: bool = Field(
        description="True iff chunks == embeddings == faiss_vectors and nothing is missing."
    )


class AIIndexStatusResponse(BaseModel):
    """Envelope for GET /api/v1/admin/ai/index-status (HTTP 200)."""

    success: bool = True
    message: str = "AI index status retrieved."
    data: AIIndexStatusData


# =============================================================================
# GET /admin/ai/health  (Phase 14: extended observability health check)
# =============================================================================


class AIHealthData(BaseModel):
    """
    Observability and health snapshot for the AI subsystem (Phase 14).

    Never exposes document contents, user data, or internal errors.
    """

    status: str = Field(description="'healthy', 'degraded', or 'unavailable'.")
    faiss_loaded: bool = Field(description="True if the FAISS index is loaded in memory.")
    faiss_vectors: int = Field(description="Number of vectors in the FAISS index.")
    consistent: bool = Field(
        description="True iff chunk count == embedding count == FAISS vector count."
    )
    missing_embeddings: int = Field(description="Chunks without embeddings (non-zero = degraded).")
    documents_with_chunks: int = Field(
        default=0,
        description="Non-deleted documents that have at least one chunk.",
    )
    embedding_model: str = Field(
        default="",
        description="Sentence-transformers model name used for embedding.",
    )
    vector_dimension: int = Field(
        default=384,
        description="Dimensionality of FAISS index vectors.",
    )
    reranker_enabled: bool = Field(
        default=False,
        description="Whether cross-encoder reranking is active (AI_RERANK_ENABLED).",
    )
    hybrid_enabled: bool = Field(
        default=True,
        description="Whether hybrid retrieval (semantic+lexical+RRF) is active (AI_HYBRID_ENABLED).",
    )
    rrf_k: int = Field(
        default=60,
        description="Reciprocal Rank Fusion constant k (AI_RRF_K).",
    )
    last_index_mtime: float | None = Field(
        default=None,
        description="Unix timestamp of last FAISS index file modification. None if no file exists.",
    )
    semantic_multiplier: int = Field(
        default=3,
        description="FAISS oversample multiplier (AI_SEMANTIC_CANDIDATE_MULTIPLIER).",
    )
    max_candidates: int = Field(
        default=60,
        description="Hard ceiling on FAISS candidates per query (AI_MAX_RETRIEVAL_CANDIDATES).",
    )
    lexical_candidates: int = Field(
        default=30,
        description="Hard ceiling on lexical candidates per query (AI_LEXICAL_CANDIDATES).",
    )


class AIHealthResponse(BaseModel):
    """Envelope for GET /api/v1/admin/ai/health (HTTP 200)."""

    success: bool = True
    message: str = "AI health retrieved."
    data: AIHealthData


# =============================================================================
# GET /admin/system/metrics (Milestone 12 System Observability Dashboard)
# =============================================================================


class SystemMetricsData(BaseModel):
    """System-wide telemetry and operational statistics."""

    status: str
    uptime_seconds: float
    memory_usage_mb: float
    environment: str
    database_status: str
    database_latency_ms: float | None = None
    redis_status: str
    redis_latency_ms: float | None = None
    celery_status: str
    ai_status: str
    faiss_vectors: int = 0
    total_users_count: int = 0
    total_documents_count: int = 0
    total_workflows_count: int = 0
    total_executions_count: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SystemMetricsResponse(BaseModel):
    """Response envelope for system telemetry metrics."""

    success: bool = True
    data: SystemMetricsData
