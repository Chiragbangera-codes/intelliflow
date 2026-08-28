"""
SearchService — semantic search business logic.

Orchestrates:
  1. Query validation
  2. Embedding generation (reuses the module-level singleton)
  3. FAISS vector search (reuses the module-level singleton)
  4. Batched PostgreSQL resolution of candidate chunk IDs
  5. Two-layer RBAC enforcement (SQL filter + in-process ownership check)
  6. Similarity score filtering
  7. Result ranking preservation
  8. Audit trail logging

Security design:
  FAISS is retrieval infrastructure, NOT an authorization mechanism.
  Two independent RBAC layers are applied after every FAISS search:

    Layer 1 — SQL (SearchRepository):
      WHERE document.owner_id = actor.id   (non-admin users)
      or no restriction                    (admin / hr)

    Layer 2 — In-process (this service):
      For every resolved chunk, verify chunk.document_owner_id == actor.id
      (admin / hr bypass this check).

  Both layers must pass.  Either alone is insufficient.

  Documents belonging to other users are NEVER mentioned in responses or
  error messages, even if FAISS ranks them above authorized results.

Score semantics:
  distance   — Raw FAISS L2 distance.  Lower = more similar.
  similarity — 1 / (1 + distance).  Range (0, 1].  Higher = more similar.
               Not cosine similarity; a bounded monotonic transform.
  min_score  — If provided, filters on similarity >= min_score.

FAISS candidate count:
  To allow RBAC filtering to remove results without depleting the output
  below top_k, FAISS is queried for min(top_k * 3, 60) candidates.
  Example: requested top_k=5 → FAISS candidates=15.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.search_repository import ChunkWithDocument, SearchRepository
from app.schemas.search import SearchData, SearchResult
from app.services.embedding_service import embedding_service
from app.services.retrieval_authorization import GLOBAL_ACCESS_ROLES
from app.services.vector_store_service import vector_store

logger = logging.getLogger(__name__)

# Roles that may access all documents globally (admin / hr bypass ownership).
# Canonical definition lives in retrieval_authorization; aliased here for the
# existing references below.
_GLOBAL_ACCESS_ROLES = GLOBAL_ACCESS_ROLES

# FAISS oversample multiplier and absolute cap
_FAISS_OVERSAMPLE_FACTOR = 3
_FAISS_CANDIDATE_CAP = 60


def _compute_similarity(distance: float) -> float:
    """
    Convert a FAISS L2 distance to a bounded human-readable similarity score.

    Formula: similarity = 1 / (1 + distance)
    Range:   (0, 1]  — 1.0 when distance == 0 (identical vectors)

    This is NOT cosine similarity.  It is a deterministic monotonic
    transform used purely for readability.  The authoritative ranking
    metric remains the raw L2 distance.
    """
    return 1.0 / (1.0 + distance)


class SearchService:
    """Semantic search orchestration with two-layer RBAC enforcement."""

    def __init__(self, db: AsyncSession) -> None:
        self._session = db
        self._search_repo = SearchRepository(db)
        self._audit_repo = AuditLogRepository(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def semantic_search(
        self,
        *,
        query: str,
        actor: User,
        top_k: int,
        min_score: float | None,
        ip_address: str | None = None,
    ) -> SearchData:
        """
        Execute a semantic search for the given query.

        Args:
            query:      Natural-language search string (pre-validated).
            actor:      Authenticated user performing the search.
            top_k:      Maximum number of authorized results to return.
            min_score:  Minimum similarity threshold (0–1). None = no filter.
            ip_address: Client IP for audit logging.

        Returns:
            SearchData with ranked, authorized results.

        Raises:
            HTTPException 422: If the query is blank or whitespace-only.
        """
        # Step 1 — Validate query
        clean_query = query.strip()
        if not clean_query:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Query must not be blank or whitespace-only.",
            )

        role_name = actor.role.name if hasattr(actor.role, "name") else str(actor.role)
        is_global = role_name in _GLOBAL_ACCESS_ROLES

        # Resolve the effective similarity threshold: an explicit per-request
        # min_score always wins; otherwise fall back to the configured default
        # (AI_MIN_RETRIEVAL_SCORE, None = no filtering).
        effective_min_score = (
            min_score if min_score is not None else settings.AI_MIN_RETRIEVAL_SCORE
        )

        logger.info(
            "Semantic search: actor=%s role=%s top_k=%d query_len=%d min_score=%s",
            actor.id,
            role_name,
            top_k,
            len(clean_query),
            effective_min_score,
        )

        # Step 2 — Generate embedding (reuse module-level singleton — no new model)
        query_vector = embedding_service.embed_text(clean_query)

        # Step 3 — Search FAISS for oversample candidates
        #   Request more candidates than top_k so RBAC filtering does not
        #   deplete the output below the requested count.
        #   Bounded to avoid scanning the entire index unnecessarily.
        faiss_k = min(top_k * _FAISS_OVERSAMPLE_FACTOR, _FAISS_CANDIDATE_CAP)
        faiss_results = vector_store.search(query_vector, top_k=faiss_k)

        if not faiss_results:
            logger.debug("FAISS returned no candidates for query (empty index or no matches).")
            await self._write_audit(
                actor=actor,
                query=clean_query,
                top_k=top_k,
                result_count=0,
                ip_address=ip_address,
            )
            return SearchData(query=clean_query, results=[], total_results=0)

        # Step 4 — Resolve candidates through PostgreSQL (single batched query)
        candidate_ids: list[uuid.UUID] = [r.chunk_id for r in faiss_results]
        # Layer 1 RBAC: SQL-level owner filter (admin/hr get None → no restriction)
        sql_owner_id = None if is_global else actor.id
        resolved: dict[
            uuid.UUID, ChunkWithDocument
        ] = await self._search_repo.get_chunks_with_documents(
            candidate_ids,
            owner_id=sql_owner_id,
        )

        # Step 5 — Build results, preserving FAISS rank order, applying RBAC Layer 2
        results: list[SearchResult] = []
        for faiss_hit in faiss_results:
            chunk_data = resolved.get(faiss_hit.chunk_id)
            if chunk_data is None:
                # Stale FAISS chunk (deleted from DB) or inaccessible — skip silently
                logger.debug(
                    "Skipping FAISS chunk_id=%s: not found in authorized DB results.",
                    faiss_hit.chunk_id,
                )
                continue

            # Layer 2 RBAC: in-process ownership check (defence-in-depth)
            # Verify the resolved document belongs to the authenticated user.
            # Admin/HR bypass this check — they have global access.
            if not is_global and chunk_data.document_owner_id != actor.id:
                logger.warning(
                    "RBAC layer-2 violation: chunk_id=%s owner=%s actor=%s — SQL filter "
                    "should have excluded this.  Dropping result.",
                    faiss_hit.chunk_id,
                    chunk_data.document_owner_id,
                    actor.id,
                )
                continue

            similarity = _compute_similarity(faiss_hit.distance)

            # Step 6 — Apply min_score filter (operates on similarity, not distance)
            if effective_min_score is not None and similarity < effective_min_score:
                logger.debug(
                    "Chunk %s excluded: similarity=%.4f < min_score=%.4f",
                    faiss_hit.chunk_id,
                    similarity,
                    effective_min_score,
                )
                continue

            results.append(
                SearchResult(
                    chunk_id=chunk_data.chunk_id,
                    document_id=chunk_data.document_id,
                    document_name=chunk_data.document_name,
                    chunk_number=chunk_data.chunk_number,
                    content=chunk_data.content,
                    distance=faiss_hit.distance,
                    similarity=similarity,
                    file_type=chunk_data.file_type,
                    created_at=chunk_data.created_at,
                )
            )

            # Stop once we have enough authorized results
            if len(results) >= top_k:
                break

        # Step 7 — Audit log (safe metadata only — no full query text stored)
        await self._write_audit(
            actor=actor,
            query=clean_query,
            top_k=top_k,
            result_count=len(results),
            ip_address=ip_address,
        )

        logger.info(
            "Semantic search complete: actor=%s results=%d/%d faiss_candidates=%d",
            actor.id,
            len(results),
            top_k,
            len(faiss_results),
        )

        return SearchData(
            query=clean_query,
            results=results,
            total_results=len(results),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_audit(
        self,
        *,
        actor: User,
        query: str,
        top_k: int,
        result_count: int,
        ip_address: str | None,
    ) -> None:
        """
        Write a search.semantic audit record.

        Stores safe metadata only:
          query_length  — length of the query (not the query text itself)
          top_k         — requested result count
          result_count  — number of authorized results returned

        The full query text is intentionally omitted unless the project's
        audit policy explicitly permits storing it.
        """
        try:
            await self._audit_repo.create(
                action="search.semantic",
                user_id=actor.id,
                table_name="document_chunks",
                new_value={
                    "query_length": len(query),
                    "top_k": top_k,
                    "result_count": result_count,
                },
                ip_address=ip_address,
            )
            await self._session.commit()
        except Exception:
            # Audit failures must never break the search response
            logger.exception("Failed to write search audit record for actor=%s", actor.id)
            try:
                await self._session.rollback()
            except Exception:
                pass
