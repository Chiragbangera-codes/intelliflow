"""
VectorStoreService — FAISS-based vector index for document chunk retrieval.

Index type: IndexFlatL2
  - Exact nearest-neighbour search (no approximation).
  - Correct and efficient at the expected data scale (thousands of chunks).
  - Combined with L2-normalized embeddings this ranks identically to cosine
    similarity but with the simpler IndexFlatL2 interface.

Persistence layout on disk:
  /app/data/faiss/
      index.faiss          ← FAISS binary index
      index_mapping.json   ← {"0": "<uuid>", "1": "<uuid>", ...}

The sidecar JSON maps FAISS row integer IDs to document_chunk UUIDs.
FAISS itself stores only float vectors; all metadata stays in PostgreSQL.

Thread-safety:
  Reads (search) and writes (add/save) are protected by a threading.RLock.
  This is adequate for the current Celery worker architecture where each
  worker process has a single index instance. Concurrent Celery tasks on the
  same worker serialise their FAISS writes through the lock.

Design constraints:
  - Never store document text inside FAISS.
  - Never silently corrupt an existing index (validate before overwriting).
  - Safe startup when no index file exists.
  - Safe startup when index is empty.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkVector:
    """A document chunk paired with its embedding vector."""

    chunk_id: uuid.UUID
    vector: list[float]


@dataclass(frozen=True)
class SearchResult:
    """One result from a FAISS similarity search."""

    chunk_id: uuid.UUID
    distance: float  # L2 distance — lower is more similar
    rank: int  # 1-based rank in the result set


# ---------------------------------------------------------------------------
# VectorStoreService
# ---------------------------------------------------------------------------


class VectorStoreService:
    """
    Manages a FAISS IndexFlatL2 for document chunk embeddings.

    Lifecycle:
        On worker startup, call load() to restore a persisted index or
        initialize an empty one. Then use add_chunks() and search().

    All public methods are thread-safe via an internal RLock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._index: Any = None  # faiss.IndexFlatL2, typed as Any to defer import
        # Maps FAISS row integer → document_chunk UUID (as string)
        self._mapping: dict[int, str] = {}
        self._dimension: int = 384  # all-MiniLM-L6-v2 output dimension
        # mtime of the on-disk index at the moment we last loaded/saved it.
        # Used to detect out-of-process writes (e.g. the worker re-embedding or
        # an admin reindex) so this process can transparently reload instead of
        # serving a stale in-memory index until restart.
        self._loaded_mtime: float | None = None

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    @property
    def _index_path(self) -> Path:
        target = Path(settings.FAISS_INDEX_PATH)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            return target
        except OSError:
            fallback = Path("/tmp/faiss")
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback / target.name

    @property
    def _mapping_path(self) -> Path:
        return self._index_path.with_name("index_mapping.json")

    def _ensure_dir(self) -> None:
        """Create the parent directory for the index if it does not exist."""
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _disk_mtime(self) -> float | None:
        """Return the on-disk index file mtime, or None if it does not exist."""
        try:
            return self._index_path.stat().st_mtime
        except OSError:
            return None

    def _ensure_current(self) -> None:
        """
        Load the index if not yet loaded, or reload it if the on-disk file has
        changed since we last loaded/saved it (must hold self._lock).

        This keeps every process (API + worker) consistent with the shared
        on-disk index without requiring a restart after an out-of-process
        rebuild. The atomic write-then-rename in save() guarantees readers see
        either the old or the new complete file, never a partial one.
        """
        if self._index is None:
            self.load()
            return
        disk_mtime = self._disk_mtime()
        if disk_mtime is not None and (
            self._loaded_mtime is None or disk_mtime > self._loaded_mtime
        ):
            logger.info(
                "FAISS on-disk index changed (mtime %s > %s) — reloading.",
                disk_mtime,
                self._loaded_mtime,
            )
            self.load()

    def reload(self) -> None:
        """Force a reload of the index from disk, discarding in-memory state."""
        with self._lock:
            self.load()

    def ensure_loaded(self) -> None:
        """
        Load the index if not yet loaded, or reload it if the on-disk file has
        changed — without performing a search.

        Public, lock-acquiring wrapper around _ensure_current() for callers such
        as the admin index-status endpoint that need vector_count to reflect the
        current on-disk index (which another process may have written) rather
        than this process's possibly-unloaded in-memory state.
        """
        with self._lock:
            self._ensure_current()

    def _import_faiss(self) -> Any:
        """Lazily import faiss so the module loads even if faiss is absent."""
        import faiss

        return faiss

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Load the FAISS index and mapping from disk, or create an empty index.

        Safe to call when no index exists — creates a fresh IndexFlatL2.
        Safe to call when the index is empty — loads it normally.
        """
        faiss = self._import_faiss()
        with self._lock:
            if self._index_path.exists() and self._mapping_path.exists():
                try:
                    self._index = faiss.read_index(str(self._index_path))
                    with open(self._mapping_path) as f:
                        raw: dict[str, str] = json.load(f)
                    self._mapping = {int(k): v for k, v in raw.items()}
                    logger.info(
                        "FAISS index loaded: path=%s vectors=%d",
                        self._index_path,
                        self._index.ntotal,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to load existing FAISS index (%s). "
                        "Starting with a fresh empty index.",
                        exc,
                    )
                    self._init_empty(faiss)
            else:
                logger.info(
                    "No existing FAISS index at '%s'. Initialising empty index.",
                    self._index_path,
                )
                self._init_empty(faiss)
            # Record the mtime of the file we just loaded (None if none existed)
            # so _ensure_current() can detect subsequent out-of-process writes.
            self._loaded_mtime = self._disk_mtime()

    def _init_empty(self, faiss: Any) -> None:
        """Create a brand-new empty IndexFlatL2 (must hold self._lock)."""
        self._index = faiss.IndexFlatL2(self._dimension)
        self._mapping = {}

    def save(self) -> None:
        """
        Atomically persist the FAISS index and mapping to disk.

        Uses a write-to-temp-then-rename strategy so a crash during write
        never leaves a half-written index behind.
        """
        faiss = self._import_faiss()
        with self._lock:
            if self._index is None:
                logger.warning("save() called before index is initialised — skipping.")
                return

            self._ensure_dir()
            unique_id = f"{os.getpid()}_{uuid.uuid4().hex}"
            tmp_index = self._index_path.parent / f"{self._index_path.name}.{unique_id}.tmp"
            tmp_mapping = self._mapping_path.parent / f"{self._mapping_path.name}.{unique_id}.tmp"

            try:
                faiss.write_index(self._index, str(tmp_index))
                with open(tmp_mapping, "w") as f:
                    json.dump({str(k): v for k, v in self._mapping.items()}, f)

                os.replace(tmp_index, self._index_path)
                os.replace(tmp_mapping, self._mapping_path)

                # We are now the freshest writer — track our own mtime so
                # _ensure_current() does not needlessly reload our own write.
                self._loaded_mtime = self._disk_mtime()

                logger.info(
                    "FAISS index saved: path=%s vectors=%d",
                    self._index_path,
                    self._index.ntotal,
                )
            except Exception:
                # Clean up temp files if save failed
                tmp_index.unlink(missing_ok=True)
                tmp_mapping.unlink(missing_ok=True)
                raise

    def build_index(self, chunks: list[ChunkVector]) -> None:
        """
        Rebuild the entire index from scratch using the provided chunks.

        Used during worker warm-up to reconstruct from AIEmbedding rows.
        Replaces any existing in-memory index; caller must call save() afterwards.

        Args:
            chunks: All chunk vectors to index.
        """
        faiss = self._import_faiss()
        with self._lock:
            self._init_empty(faiss)
            if not chunks:
                logger.info("build_index called with 0 chunks — empty index created.")
                return

            vectors = np.array([c.vector for c in chunks], dtype=np.float32)
            self._index.add(vectors)
            self._mapping = {i: str(c.chunk_id) for i, c in enumerate(chunks)}
            logger.info(
                "FAISS index rebuilt with %d vectors.",
                self._index.ntotal,
            )

    def add_chunks(self, chunks: list[ChunkVector]) -> None:
        """
        Incrementally add new chunk vectors to the existing index.

        The new vectors are appended; existing rows are never modified.
        Caller must call save() to persist the updated index.

        Args:
            chunks: New chunk vectors to add.
        """
        if not chunks:
            return

        with self._lock:
            self._ensure_current()
            assert self._index is not None

            base_row = self._index.ntotal
            vectors = np.array([c.vector for c in chunks], dtype=np.float32)
            self._index.add(vectors)

            for offset, chunk in enumerate(chunks):
                self._mapping[base_row + offset] = str(chunk.chunk_id)

            logger.debug(
                "FAISS: added %d vectors. Total: %d.",
                len(chunks),
                self._index.ntotal,
            )

    def search(self, query_vector: list[float], top_k: int | None = None) -> list[SearchResult]:
        """
        Find the top-k nearest chunks for a query vector.

        Args:
            query_vector: Embedded query (same dimension as indexed vectors).
            top_k: Number of results to return. Defaults to settings.RAG_TOP_K.

        Returns:
            List of SearchResult ordered by ascending L2 distance (most
            similar first). Returns fewer results if the index contains fewer
            vectors than top_k. Returns empty list on empty index.
        """
        k = top_k if top_k is not None else settings.RAG_TOP_K
        with self._lock:
            self._ensure_current()
            assert self._index is not None

            if self._index.ntotal == 0:
                logger.debug("FAISS search on empty index — returning [].")
                return []

            effective_k = min(k, self._index.ntotal)
            query = np.array([query_vector], dtype=np.float32)

            distances, indices = self._index.search(query, effective_k)

            results: list[SearchResult] = []
            for rank, (dist, idx) in enumerate(
                zip(distances[0], indices[0], strict=False), start=1
            ):
                if idx == -1:
                    # FAISS returns -1 when fewer results than k exist
                    continue
                chunk_id_str = self._mapping.get(int(idx))
                if chunk_id_str is None:
                    logger.warning("FAISS returned row %d with no mapping entry — skipping.", idx)
                    continue
                results.append(
                    SearchResult(
                        chunk_id=uuid.UUID(chunk_id_str),
                        distance=float(dist),
                        rank=rank,
                    )
                )
            return results

    @property
    def vector_count(self) -> int:
        """Return the number of vectors currently stored in the index."""
        with self._lock:
            if self._index is None:
                return 0
            return int(self._index.ntotal)

    @property
    def is_loaded(self) -> bool:
        """Return True if the index has been initialised (even if empty)."""
        with self._lock:
            return self._index is not None


# ---------------------------------------------------------------------------
# Module-level singleton — shared across the worker process
# ---------------------------------------------------------------------------
vector_store = VectorStoreService()


async def warm_up_vector_store() -> int:
    """
    Ensure the FAISS vector store is initialized, loaded, and synchronized.

    Resilience strategy for cloud deployments (Render, Railway, Fly.io, etc.):
    1. If FAISS index and mapping exist on disk and vector_count > 0:
       Loads the index directly (0ms fast path).
    2. If index file is missing OR contains 0 vectors while PostgreSQL contains
       active chunk embeddings (e.g. fresh ephemeral container deployment):
       Rebuilds the index from database embeddings and persists to disk.
    3. If no embeddings exist in the database:
       Safely initializes an empty index.

    Returns:
        The number of vectors in the active index.
    """
    if not settings.FAISS_AUTO_WARMUP:
        logger.info("FAISS auto-warmup disabled by configuration.")
        vector_store.ensure_loaded()
        return vector_store.vector_count

    index_path = Path(settings.FAISS_INDEX_PATH)

    # 1. Fast path: load from disk if present
    if index_path.exists():
        vector_store.load()
        if vector_store.vector_count > 0 or not settings.FAISS_AUTO_REBUILD_ON_EMPTY:
            logger.info(
                "FAISS warm-up: index loaded from disk with %d vectors (path: %s).",
                vector_store.vector_count,
                index_path,
            )
            return vector_store.vector_count
        logger.info(
            "FAISS warm-up: index file exists at '%s' but contains 0 vectors. "
            "Checking database to self-heal.",
            index_path,
        )
    else:
        logger.info(
            "FAISS warm-up: index file not found at '%s'. "
            "Checking database for embeddings to construct index.",
            index_path,
        )

    # 2. Self-healing rebuild from PostgreSQL
    try:
        from app.core.database import AsyncSessionLocal
        from app.repositories.ai_embedding_repository import AIEmbeddingRepository
        from app.services.embedding_service import embedding_service

        async with AsyncSessionLocal() as session:
            repo = AIEmbeddingRepository(session)
            all_embeddings = await repo.get_all_with_chunks()

        valid = [(emb, emb.chunk) for emb in all_embeddings if emb.chunk is not None]
        if not valid:
            logger.info("FAISS warm-up: no active embedding records in database — empty index ready.")
            vector_store.load()
            return 0

        logger.info(
            "FAISS warm-up: found %d embedding records in database. Constructing FAISS index.",
            len(valid),
        )
        texts = [chunk.content for _, chunk in valid]
        vectors = embedding_service.embed_batch(texts)

        chunk_vectors = [
            ChunkVector(chunk_id=chunk.id, vector=vec)
            for (_, chunk), vec in zip(valid, vectors, strict=False)
        ]

        vector_store.build_index(chunk_vectors)
        vector_store.save()

        logger.info(
            "FAISS warm-up complete: %d vectors indexed and saved to %s.",
            vector_store.vector_count,
            index_path,
        )
        return vector_store.vector_count

    except Exception as exc:
        logger.warning(
            "FAISS warm-up failed during database self-healing (%s). "
            "Initializing empty fallback index.",
            exc,
        )
        vector_store.load()
        return vector_store.vector_count
