"""
Celery application instance.

Configures the Celery app and registers all background task modules.

Task modules:
  app.workers.ocr_tasks   — document OCR & text extraction (Milestone 6)
  app.workers.ai_tasks    — document embedding & FAISS indexing (Milestone 7)

Worker warm-up:
  On worker startup (worker_ready signal), the FAISS index is loaded from disk
  or rebuilt from AIEmbedding records in PostgreSQL. If warm-up fails the
  worker continues running so that new embedding tasks can still be processed.
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_process_init, worker_ready

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.repositories.ai_embedding_repository import AIEmbeddingRepository
from app.services.vector_store_service import ChunkVector, vector_store
from app.workers.task_runner import run_in_worker

logger = logging.getLogger(__name__)

celery_app = Celery(
    "intelliflow",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.ocr_tasks",
        "app.workers.ai_tasks",
        "app.workers.workflow_tasks",  # Milestone 8 — Workflow Engine
        "app.workers.report_tasks",  # Milestone 9 — Report Generation
        "app.workers.document_tasks",  # Milestone 11 — Document Intelligence
        "app.workers.event_tasks",  # Milestone 13 — Event Bus & Integrations
    ],
)

celery_app.conf.update(
    # Serialization — JSON is human-readable and safe
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone — always UTC to match the database convention
    timezone="UTC",
    enable_utc=True,
    # Task result expiry — results are kept for 1 hour by default
    result_expires=3600,
    # Worker configuration
    worker_prefetch_multiplier=1,  # Fair task distribution
    task_acks_late=True,  # Acknowledge after completion, not on pickup
    task_reject_on_worker_lost=True,
    # Task Timeouts & Reliability (Milestone 12)
    task_soft_time_limit=300,  # 5 min soft timeout
    task_time_limit=360,  # 6 min hard timeout
    worker_max_tasks_per_child=100,  # Prevent memory leaks from PyTorch/FAISS
)


# ---------------------------------------------------------------------------
# Worker process lifecycle signals
# ---------------------------------------------------------------------------


@worker_process_init.connect
def on_worker_process_init(**kwargs: object) -> None:
    """Reset the SQLAlchemy engine pool in child worker processes post-fork."""
    try:
        engine.sync_engine.dispose()
        logger.debug("Worker process initialized — database engine pool disposed.")
    except Exception as exc:
        logger.warning("Failed to dispose database engine pool on worker process init: %s", exc)


@worker_ready.connect
def on_worker_ready(**kwargs: object) -> None:
    """
    Signal handler: runs when the Celery worker is fully started.

    Loads or rebuilds the FAISS index from persisted AIEmbedding records.
    Failures are caught and logged; the worker continues regardless.
    """
    logger.info("Worker ready — starting FAISS index warm-up.")
    try:
        run_in_worker(_warm_up_faiss())
    except Exception as exc:
        logger.error(
            "FAISS warm-up failed: %s. "
            "The worker will continue — existing embeddings may not be searchable "
            "until the index is rebuilt by the next successful embedding task.",
            exc,
        )


async def _warm_up_faiss() -> None:
    """
    Async warm-up: load the FAISS index from disk or rebuild from PostgreSQL.

    Strategy:
      1. If index.faiss exists on disk → load it (fast path).
      2. If index is missing or stale → rebuild from AIEmbedding rows in DB.
      3. Log the final vector count and index path.
    """
    from pathlib import Path

    index_path = Path(settings.FAISS_INDEX_PATH)

    if index_path.exists():
        logger.info("FAISS warm-up: loading existing index from '%s'.", index_path)
        vector_store.load()
        logger.info(
            "FAISS warm-up: index loaded. Vectors: %d. Path: %s.",
            vector_store.vector_count,
            index_path,
        )
        return

    # Index file missing — rebuild from DB embeddings
    logger.info(
        "FAISS warm-up: index file not found at '%s'. "
        "Rebuilding from AIEmbedding records in PostgreSQL.",
        index_path,
    )

    async with AsyncSessionLocal() as session:
        repo = AIEmbeddingRepository(session)
        all_embeddings = await repo.get_all_with_chunks()

    if not all_embeddings:
        logger.info(
            "FAISS warm-up: no AIEmbedding records found. "
            "Starting with an empty index (no documents have been embedded yet)."
        )
        vector_store.load()  # initialises empty index
        return

    logger.info(
        "FAISS warm-up: found %d embedding records. " "Re-embedding chunks to rebuild index.",
        len(all_embeddings),
    )

    from app.services.embedding_service import embedding_service

    # Filter out records whose chunks were deleted
    valid = [(emb, emb.chunk) for emb in all_embeddings if emb.chunk is not None]
    if not valid:
        logger.warning("FAISS warm-up: all embedding records have missing chunks — empty index.")
        vector_store.load()
        return

    texts = [chunk.content for _, chunk in valid]
    vectors = embedding_service.embed_batch(texts)

    chunk_vectors = [
        ChunkVector(chunk_id=chunk.id, vector=vec)
        for (_, chunk), vec in zip(valid, vectors, strict=False)
    ]

    vector_store.load()  # initialise the store before calling build_index
    vector_store.build_index(chunk_vectors)
    vector_store.save()

    logger.info(
        "FAISS warm-up: index rebuilt with %d vectors. Path: %s.",
        vector_store.vector_count,
        settings.FAISS_INDEX_PATH,
    )
