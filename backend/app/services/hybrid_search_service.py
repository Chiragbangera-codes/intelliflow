"""
HybridSearchService — semantic + lexical retrieval fused with Reciprocal Rank
Fusion (RRF), gated by PostgreSQL authorization.

Pipeline (Milestone 7 Phase 1/3/4):
    query
      → semantic candidates (embed → FAISS)      ┐
      → lexical candidates  (PostgreSQL FTS/LIKE) ┤ generators
      → doc-aware candidates (filename lookup)    ┘
      → RRF fusion                (rank-based, order-agnostic)
      → authorization filtering   (PostgreSQL ownership — AUTHORITATIVE)
      → relevance threshold       (min_score, applied to semantic scores only)
      → top_k
      → SearchData

Reciprocal Rank Fusion:
    RRF_score(d) = Σ_branches  1 / (k + rank_branch(d))
    with k = settings.AI_RRF_K (default 60). RRF depends only on a document's
    RANK within each branch, never on the branches' incomparable raw scores
    (L2 distance vs ts_rank), which is exactly why it is robust for fusing
    heterogeneous retrievers.

Security (verbatim intent — Phase 1/23):
  - FAISS and the lexical index are candidate GENERATORS, never authorization
    layers. Every fused candidate is resolved through retrieval_authorization
    (PostgreSQL ownership + soft-delete exclusion, two layers) before any
    content, filename, metadata, or score is returned. Unauthorized or stale
    candidates vanish silently — their existence is never revealed.
  - min_score is a similarity (semantic) threshold; it filters only candidates
    that carry a similarity. Lexical-only exact matches are kept, since a
    keyword/filename hit is a strong signal that has no similarity to compare.

Bounds (no magic constants — all from settings):
  - semantic candidates: min(top_k * AI_SEMANTIC_CANDIDATE_MULTIPLIER,
                             AI_MAX_RETRIEVAL_CANDIDATES)
  - lexical candidates:  AI_LEXICAL_CANDIDATES
  - final results:       top_k
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lexical_search_repository import LexicalMatch, LexicalSearchRepository
from app.repositories.search_repository import ChunkWithDocument, SearchRepository
from app.schemas.search import SearchData, SearchResult
from app.services.embedding_service import embedding_service
from app.services.query_analyzer import extract_filename_terms
from app.services.reranker_service import reranker_service
from app.services.retrieval_authorization import (
    authorize_chunks,
    is_global_access,
    sql_owner_filter,
)
from app.services.search_service import _compute_similarity
from app.services.vector_store_service import SearchResult as FAISSHit
from app.services.vector_store_service import vector_store

logger = logging.getLogger(__name__)


@dataclass
class _Fused:
    """Mutable per-chunk fusion accumulator (internal to this service)."""

    chunk_id: uuid.UUID
    rrf_score: float = 0.0
    distance: float | None = None
    similarity: float | None = None
    in_semantic: bool = False
    in_lexical: bool = False
    in_doc_aware: bool = False

    @property
    def match_type(self) -> str:
        # Semantic (meaning) vs keyword-family signals (lexical FTS + filename
        # doc-aware). A chunk found by both families is "hybrid".
        keyword_family = self.in_lexical or self.in_doc_aware
        if self.in_semantic and keyword_family:
            return "hybrid"
        return "semantic" if self.in_semantic else "lexical"


class HybridSearchService:
    """Hybrid (semantic + lexical) retrieval with authoritative RBAC."""

    def __init__(self, db: AsyncSession) -> None:
        self._session = db
        self._search_repo = SearchRepository(db)
        self._lexical_repo = LexicalSearchRepository(db)
        self._audit_repo = AuditLogRepository(db)
        self._reranker = reranker_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        *,
        query: str,
        actor: User,
        top_k: int,
        min_score: float | None = None,
        ip_address: str | None = None,
        write_audit: bool = True,
    ) -> SearchData:
        """
        Execute hybrid retrieval and return ranked, authorized results.

        Args:
            query:       Natural-language query (validated here).
            actor:       Authenticated user.
            top_k:       Maximum authorized results to return.
            min_score:   Similarity threshold; None falls back to
                         settings.AI_MIN_RETRIEVAL_SCORE.
            ip_address:  Client IP for the audit record.
            write_audit: When True, write a search.hybrid audit record. RAG
                         disables this because it writes its own ai.chat record.

        Raises:
            HTTPException 422: blank/whitespace-only query.
        """
        clean_query = query.strip()
        if not clean_query:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Query must not be blank or whitespace-only.",
            )

        is_global = is_global_access(actor)
        owner_id = sql_owner_filter(actor)
        effective_min_score = (
            min_score if min_score is not None else settings.AI_MIN_RETRIEVAL_SCORE
        )

        faiss_k = min(
            top_k * settings.AI_SEMANTIC_CANDIDATE_MULTIPLIER,
            settings.AI_MAX_RETRIEVAL_CANDIDATES,
        )
        lexical_limit = settings.AI_LEXICAL_CANDIDATES
        hybrid_enabled = settings.AI_HYBRID_ENABLED

        logger.info(
            "Hybrid search: actor=%s global=%s top_k=%d query_len=%d hybrid=%s "
            "faiss_k=%d lexical_k=%d min_score=%s",
            actor.id,
            is_global,
            top_k,
            len(clean_query),
            hybrid_enabled,
            faiss_k,
            lexical_limit,
            effective_min_score,
        )

        semantic, lexical, doc_aware = await self._gather_candidates(
            query=clean_query,
            owner_id=owner_id,
            faiss_k=faiss_k,
            lexical_limit=lexical_limit,
            hybrid_enabled=hybrid_enabled,
            top_k=top_k,
        )

        fused = self._fuse(semantic, lexical, doc_aware)

        if not fused:
            if write_audit:
                await self._write_audit(
                    actor=actor,
                    query=clean_query,
                    top_k=top_k,
                    result_count=0,
                    semantic_count=len(semantic),
                    lexical_count=len(lexical),
                    doc_aware_count=len(doc_aware),
                    ip_address=ip_address,
                )
            return SearchData(query=clean_query, results=[], total_results=0)

        # AUTHORITATIVE gate: resolve every fused candidate through PostgreSQL
        # ownership. Nothing beyond this point can reference an unauthorized doc.
        authorized = await authorize_chunks(self._search_repo, list(fused.keys()), actor=actor)

        results = self._rank_and_build(
            fused=fused,
            authorized=authorized,
            effective_min_score=effective_min_score,
        )

        # Optional cross-encoder rerank (Phase 5): sharpen the ordering of the
        # leading candidates, then bound to top_k. Pure pass-through (and no
        # model load) when AI_RERANK_ENABLED is False — the default.
        results = self._reranker.rerank(
            query=clean_query, results=results, top_n=settings.AI_RERANK_TOP_N
        )
        results = results[:top_k]

        if write_audit:
            await self._write_audit(
                actor=actor,
                query=clean_query,
                top_k=top_k,
                result_count=len(results),
                semantic_count=len(semantic),
                lexical_count=len(lexical),
                doc_aware_count=len(doc_aware),
                ip_address=ip_address,
            )

        logger.info(
            "Hybrid search complete: actor=%s results=%d/%d semantic=%d lexical=%d doc_aware=%d",
            actor.id,
            len(results),
            top_k,
            len(semantic),
            len(lexical),
            len(doc_aware),
        )
        return SearchData(query=clean_query, results=results, total_results=len(results))

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------

    async def _gather_candidates(
        self,
        *,
        query: str,
        owner_id: uuid.UUID | None,
        faiss_k: int,
        lexical_limit: int,
        hybrid_enabled: bool,
        top_k: int,
    ) -> tuple[list[FAISSHit], list[LexicalMatch], list[LexicalMatch]]:
        """
        Produce semantic, lexical, and document-aware candidate lists.

        Concurrency model: the semantic branch (embedding + FAISS) is CPU-bound
        and touches NO DB session, so it runs in a worker thread. The lexical
        and document-aware branches are both DB queries on self._session; an
        AsyncSession cannot be used concurrently, so they run sequentially while
        the semantic thread overlaps with both. This is the only safe overlap.

        When hybrid is disabled the retriever degrades to semantic-only — the
        keyword-family branches (lexical + doc-aware) are skipped entirely.
        """
        if not hybrid_enabled:
            semantic = await asyncio.to_thread(self._semantic_candidates, query, faiss_k)
            return semantic, [], []

        # Kick off the CPU-bound semantic branch in a thread; it runs while the
        # DB branches below execute on the event loop.
        semantic_task = asyncio.create_task(
            asyncio.to_thread(self._semantic_candidates, query, faiss_k)
        )

        # Serialise the two DB branches on the shared session.
        lexical = await self._lexical_candidates(
            query=query, owner_id=owner_id, limit=lexical_limit
        )
        doc_aware = await self._doc_aware_candidates(query=query, owner_id=owner_id, top_k=top_k)

        semantic = await semantic_task
        return semantic, lexical, doc_aware

    def _semantic_candidates(self, query: str, faiss_k: int) -> list[FAISSHit]:
        """Embed the query and fetch FAISS neighbours (runs in a thread)."""
        if faiss_k < 1:
            return []
        query_vector = embedding_service.embed_text(query)
        return vector_store.search(query_vector, top_k=faiss_k)

    async def _lexical_candidates(
        self, *, query: str, owner_id: uuid.UUID | None, limit: int
    ) -> list[LexicalMatch]:
        """Fetch lexical matches (owner-filtered in SQL — Layer 1)."""
        return await self._lexical_repo.search(query=query, owner_id=owner_id, limit=limit)

    async def _doc_aware_candidates(
        self, *, query: str, owner_id: uuid.UUID | None, top_k: int
    ) -> list[LexicalMatch]:
        """
        Document-aware branch (Phase 4): if the query names a document, fetch
        that document's leading chunks so it surfaces even when the other
        branches missed it. Generic — matches query terms against actual
        filenames in SQL (owner-filtered); hardcodes nothing.
        """
        if not settings.AI_DOC_AWARE_ENABLED:
            return []
        terms = extract_filename_terms(query)
        if not terms:
            return []
        return await self._lexical_repo.search_by_filename(
            terms=terms,
            owner_id=owner_id,
            chunks_per_doc=settings.AI_DOC_AWARE_CHUNKS_PER_DOC,
            max_docs=top_k,
        )

    # ------------------------------------------------------------------
    # Fusion + ranking
    # ------------------------------------------------------------------

    def _fuse(
        self,
        semantic: list[FAISSHit],
        lexical: list[LexicalMatch],
        doc_aware: list[LexicalMatch],
    ) -> dict[uuid.UUID, _Fused]:
        """
        Combine the ranked branch lists into per-chunk RRF accumulators.

        Each branch contributes 1/(k + rank) independently, so a chunk found by
        multiple branches accrues more rank mass. The document-aware branch is a
        full RRF participant: this is how an explicitly-named document is
        "boosted" — not by an ad-hoc multiplier, but by earning a third vote.
        """
        k = settings.AI_RRF_K
        fused: dict[uuid.UUID, _Fused] = {}

        for hit in semantic:
            entry = fused.setdefault(hit.chunk_id, _Fused(chunk_id=hit.chunk_id))
            entry.rrf_score += 1.0 / (k + hit.rank)
            entry.distance = hit.distance
            entry.similarity = _compute_similarity(hit.distance)
            entry.in_semantic = True

        for match in lexical:
            entry = fused.setdefault(match.chunk_id, _Fused(chunk_id=match.chunk_id))
            entry.rrf_score += 1.0 / (k + match.rank)
            entry.in_lexical = True

        for match in doc_aware:
            entry = fused.setdefault(match.chunk_id, _Fused(chunk_id=match.chunk_id))
            entry.rrf_score += 1.0 / (k + match.rank)
            entry.in_doc_aware = True

        return fused

    def _rank_and_build(
        self,
        *,
        fused: dict[uuid.UUID, _Fused],
        authorized: dict[uuid.UUID, ChunkWithDocument],
        effective_min_score: float | None,
    ) -> list[SearchResult]:
        """
        Order authorized candidates by fused relevance and materialise results.

        Returns the FULL threshold-filtered candidate list (not yet bounded to
        top_k): the caller reranks it and only then truncates, so reranking can
        see more than the final top_k.

        Deterministic ordering: RRF score desc, then similarity desc (semantic
        first on ties), then chunk_id asc as a stable final tiebreak.
        """
        ordered = sorted(
            (f for cid, f in fused.items() if cid in authorized),
            key=lambda f: (-f.rrf_score, -(f.similarity or 0.0), str(f.chunk_id)),
        )

        results: list[SearchResult] = []
        for f in ordered:
            # min_score is a semantic threshold: apply only when a similarity
            # exists. Lexical-only matches (similarity is None) are kept.
            if (
                effective_min_score is not None
                and f.similarity is not None
                and f.similarity < effective_min_score
            ):
                continue

            chunk = authorized[f.chunk_id]
            results.append(
                SearchResult(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    document_name=chunk.document_name,
                    chunk_number=chunk.chunk_number,
                    content=chunk.content,
                    file_type=chunk.file_type,
                    created_at=chunk.created_at,
                    distance=f.distance,
                    similarity=f.similarity,
                    score=f.rrf_score,
                    match_type=f.match_type,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    async def _write_audit(
        self,
        *,
        actor: User,
        query: str,
        top_k: int,
        result_count: int,
        semantic_count: int,
        lexical_count: int,
        doc_aware_count: int,
        ip_address: str | None,
    ) -> None:
        """Write a search.hybrid audit record — safe metadata only, no query text."""
        try:
            await self._audit_repo.create(
                action="search.hybrid",
                user_id=actor.id,
                table_name="document_chunks",
                new_value={
                    "query_length": len(query),
                    "top_k": top_k,
                    "result_count": result_count,
                    "semantic_candidates": semantic_count,
                    "lexical_candidates": lexical_count,
                    "doc_aware_candidates": doc_aware_count,
                },
                ip_address=ip_address,
            )
            await self._session.commit()
        except Exception:
            logger.exception("Failed to write hybrid search audit record for actor=%s", actor.id)
            try:
                await self._session.rollback()
            except Exception:
                pass
