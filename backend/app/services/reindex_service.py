"""
ReindexService — rebuild all embeddings and the FAISS index from PostgreSQL.

This is the single source of truth for the "heal every document's embeddings"
operation. It is invoked from three places, all of which share this logic:

  1. The CLI script `scripts/reconcile_embeddings.py` (manual, one-off).
  2. The Celery task `tasks.reindex_all_embeddings` (admin endpoint dispatch).
  3. Tests, which call `reindex_all_embeddings(session)` directly.

The invariant it restores:
    non-deleted document with chunks  ⇒  chunks == embeddings == FAISS vectors

Idempotent: safe to run repeatedly. It re-embeds every chunk of every
non-deleted document, replaces that document's ai_embeddings rows, then rebuilds
the FAISS index from scratch (dropping any stale/orphan vectors) and saves it
atomically. Because build_index() replaces the whole index, repeated runs
converge on the same vector count — no duplication.

The caller owns the AsyncSession lifecycle. This function flushes per document
and commits once at the end; it does NOT dispose the engine.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.repositories.ai_embedding_repository import AIEmbeddingRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.services.embedding_service import embedding_service
from app.services.vector_store_service import ChunkVector, vector_store

logger = logging.getLogger(__name__)


async def reindex_all_embeddings(session: AsyncSession) -> dict[str, Any]:
    """
    Rebuild all embeddings + the FAISS index from PostgreSQL. Returns a report.

    Args:
        session: An open AsyncSession. Committed once on success by this call.

    Returns:
        A report dict with counts and a per-document breakdown.
    """
    report: dict[str, Any] = {
        "documents_processed": 0,
        "documents_skipped_no_chunks": 0,
        "chunks_processed": 0,
        "embeddings_created": 0,
        "vectors_indexed": 0,
        "faiss_vectors_before": 0,
        "stale_vectors_removed": 0,
        "failures": 0,
        "per_document": [],
    }

    all_vectors: list[ChunkVector] = []
    new_chunk_ids: set[str] = set()

    # Snapshot the pre-existing FAISS state so we can report what was stale.
    vector_store.load()
    report["faiss_vectors_before"] = vector_store.vector_count
    old_mapping_chunk_ids = set(vector_store._mapping.values())  # noqa: SLF001 (diagnostic only)

    chunk_repo = DocumentChunkRepository(session)
    emb_repo = AIEmbeddingRepository(session)

    docs = (
        (
            await session.execute(
                select(Document)
                .where(Document.deleted_at.is_(None))
                .order_by(Document.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    for doc in docs:
        chunks = await chunk_repo.get_chunks_by_document(doc.id)
        if not chunks:
            report["documents_skipped_no_chunks"] += 1
            continue

        try:
            texts = [c.content for c in chunks]
            vectors = embedding_service.embed_batch(texts)

            # Idempotent replace of this document's embedding rows.
            await emb_repo.delete_by_document_id(doc.id)
            for chunk, vector in zip(chunks, vectors, strict=False):
                await emb_repo.create(
                    document_chunk_id=chunk.id,
                    vector_reference=str(chunk.id),
                    embedding_model=settings.EMBEDDING_MODEL,
                )
                all_vectors.append(ChunkVector(chunk_id=chunk.id, vector=vector))
                new_chunk_ids.add(str(chunk.id))

            await session.flush()

            report["documents_processed"] += 1
            report["chunks_processed"] += len(chunks)
            report["embeddings_created"] += len(chunks)
            report["per_document"].append({"file_name": doc.file_name, "chunks": len(chunks)})
            logger.info("Reindex: embedded %-45s %d chunks", doc.file_name, len(chunks))
        except Exception:  # noqa: BLE001
            report["failures"] += 1
            logger.exception("Reindex: failed to embed document %s (%s)", doc.id, doc.file_name)

    # Rebuild FAISS from scratch — this drops any stale/orphan vectors.
    vector_store.build_index(all_vectors)
    vector_store.save()
    report["vectors_indexed"] = vector_store.vector_count

    # A stale vector = present in the OLD FAISS mapping but not re-indexed now.
    report["stale_vectors_removed"] = len(old_mapping_chunk_ids - new_chunk_ids)

    await session.commit()

    logger.info(
        "Reindex complete: docs=%d chunks=%d vectors=%d stale_removed=%d failures=%d",
        report["documents_processed"],
        report["chunks_processed"],
        report["vectors_indexed"],
        report["stale_vectors_removed"],
        report["failures"],
    )
    return report
