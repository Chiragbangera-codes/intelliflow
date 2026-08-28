"""
LexicalSearchRepository — keyword/full-text retrieval over document chunks.

This is the lexical half of hybrid retrieval (the semantic half lives in
VectorStoreService + SearchService). It finds chunks whose *text* matches the
query terms, complementing the semantic branch which finds chunks whose
*meaning* is close. Fusing the two (see HybridSearchService) recovers exact
keyword / filename / rare-token matches that pure vector search often misses.

Dialect-aware by design:
  - PostgreSQL (production): native full-text search via to_tsvector /
    websearch_to_tsquery / ts_rank. websearch_to_tsquery parses arbitrary user
    input safely (it never raises on bad syntax), so no query sanitising is
    needed. At the current scale (thousands of chunks) an on-the-fly
    to_tsvector is fast enough; a GIN index is documented as an enable-later
    optimisation rather than shipped as a migration.
  - SQLite (unit tests / offline fallback): a parameterised term-overlap LIKE
    strategy, since SQLite has no tsvector. Ranked by how many query terms a
    chunk matches.

Security (authoritative rules — see Phase 1/23):
  - FAISS is NEVER an authorization layer; PostgreSQL ownership is. This
    repository applies the Layer-1 owner filter *in SQL*: when owner_id is
    provided (employee/manager) only that owner's non-deleted documents are
    considered; when owner_id is None (admin/HR global access) all non-deleted
    documents are considered. Soft-deleted documents (deleted_at IS NOT NULL)
    are always excluded.
  - No raw string-concatenated SQL. Every value — query terms included — is
    bound as a parameter. Query terms are tokenised to alphanumeric words, so
    LIKE metacharacters (%, _) can never reach the pattern.

Performance:
  - One batched SQL statement per search (JOIN document_chunks → documents).
    No N+1. Results are bounded by an explicit `limit`.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from functools import reduce

from sqlalchemy import ColumnElement, Integer, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

# Match runs of word characters excluding underscore. Tokenising this way
# strips LIKE metacharacters (%, _) and punctuation, so a bound term can never
# alter the LIKE pattern's meaning.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Upper bound on distinct query terms considered. Keeps the SQLite fallback's
# per-term CASE expansion (and the PG tsquery) bounded regardless of input size.
_MAX_QUERY_TERMS = 32

# PostgreSQL text-search configuration. "simple" avoids language-specific
# stemming/stop-word removal so rare tokens and filenames match literally.
_TS_CONFIG = "simple"


@dataclass(frozen=True)
class LexicalMatch:
    """
    One lexical retrieval candidate.

    Deliberately lean and parallel to vector_store.SearchResult: identifies a
    chunk plus its position in the lexical ranking. Full chunk/document metadata
    is resolved once, downstream, through the authorization-enforcing
    SearchRepository.get_chunks_with_documents — never trusted from here.
    """

    chunk_id: uuid.UUID
    rank: int  # 1-based; best lexical match first
    score: float  # ts_rank (PG) or matched-term count (SQLite); higher is better


class LexicalSearchRepository:
    """Keyword/full-text search over non-deleted, owner-scoped document chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        *,
        query: str,
        owner_id: uuid.UUID | None,
        limit: int,
    ) -> list[LexicalMatch]:
        """
        Return the top lexical matches for `query`, ranked best-first.

        Args:
            query:    Raw user query text. Tokenised internally.
            owner_id: Layer-1 RBAC filter. When set, only this owner's
                      documents are searched (employee/manager). When None,
                      all non-deleted documents are searched (admin/HR).
            limit:    Maximum candidates to return (bounded budget).

        Returns:
            List of LexicalMatch ordered by descending relevance. Empty list
            when the query has no usable terms or nothing matches.
        """
        terms = self._tokenize(query)
        if not terms or limit < 1:
            return []

        dialect = self._dialect_name()
        if dialect == "postgresql":
            rows = await self._search_postgres(query=query, owner_id=owner_id, limit=limit)
        else:
            rows = await self._search_like(terms=terms, owner_id=owner_id, limit=limit)

        return [
            LexicalMatch(chunk_id=chunk_id, rank=rank, score=float(score))
            for rank, (chunk_id, score) in enumerate(rows, start=1)
        ]

    async def search_by_filename(
        self,
        *,
        terms: list[str],
        owner_id: uuid.UUID | None,
        chunks_per_doc: int,
        max_docs: int,
    ) -> list[LexicalMatch]:
        """
        Document-aware lookup (Phase 4): return the leading chunks of documents
        whose *filename* matches the query terms, best-matching document first.

        This is the third hybrid branch. It exists so a query that names a
        document ("what's in the onboarding roadmap?") surfaces that document's
        opening chunks even when semantic/lexical ranked them low.

        Ranking:
          - Documents are scored by how many distinct `terms` appear in the
            filename; higher-scoring documents rank first (capped at max_docs).
          - Within a document the first `chunks_per_doc` chunks (lowest
            chunk_number) are taken, via a windowed ROW_NUMBER — one batched,
            bounded statement, no N+1.

        Security: owner_id applies the Layer-1 filter in SQL and soft-deleted
        documents are excluded, identical to `search`. The authoritative gate
        still runs downstream (HybridSearchService → authorize_chunks); this
        method is only a candidate generator.

        Args:
            terms:          Filename-candidate terms (from query_analyzer).
            owner_id:       Layer-1 RBAC filter (None = admin/HR global).
            chunks_per_doc: Max leading chunks per matched document.
            max_docs:       Max matched documents to consider.

        Returns:
            LexicalMatch list ranked best-first; empty when nothing matches.
        """
        if not terms or chunks_per_doc < 1 or max_docs < 1:
            return []

        # Defensive bound; callers already cap, but never trust the input size.
        terms = terms[:_MAX_QUERY_TERMS]

        # Per-document match strength = count of distinct terms present in the
        # filename. Each pattern is bound as a parameter (never concatenated).
        match_conditions: list[ColumnElement[bool]] = []
        score_terms: list[ColumnElement[int]] = []
        for term in terms:
            pattern = f"%{term}%"
            cond = Document.file_name.ilike(pattern)
            match_conditions.append(cond)
            score_terms.append(case((cond, 1), else_=0))
        score_expr = reduce(lambda a, b: a + b, score_terms).cast(Integer)

        doc_query = select(Document.id.label("doc_id"), score_expr.label("match_score")).where(
            Document.deleted_at.is_(None), or_(*match_conditions)
        )
        doc_query = self._apply_owner_filter(doc_query, owner_id)
        matched_docs = (
            doc_query.order_by(score_expr.desc(), Document.id.asc()).limit(max_docs).subquery()
        )

        # Take only the first `chunks_per_doc` chunks of each matched document.
        row_number = func.row_number().over(
            partition_by=DocumentChunk.document_id,
            order_by=DocumentChunk.chunk_number.asc(),
        )
        ranked = (
            select(
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.chunk_number.label("chunk_number"),
                matched_docs.c.match_score.label("match_score"),
                row_number.label("rn"),
            )
            .join(matched_docs, matched_docs.c.doc_id == DocumentChunk.document_id)
            .subquery()
        )
        stmt = (
            select(ranked.c.chunk_id, ranked.c.match_score)
            .where(ranked.c.rn <= chunks_per_doc)
            .order_by(
                ranked.c.match_score.desc(),
                ranked.c.chunk_number.asc(),
                ranked.c.chunk_id.asc(),
            )
        )

        result = await self._session.execute(stmt)
        return [
            LexicalMatch(chunk_id=row[0], rank=rank, score=float(row[1]))
            for rank, row in enumerate(result.all(), start=1)
        ]

    # ------------------------------------------------------------------
    # Dialect branches
    # ------------------------------------------------------------------

    async def _search_postgres(
        self,
        *,
        query: str,
        owner_id: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        """PostgreSQL full-text search over chunk content + document filename."""
        # Combine chunk text and filename into one searchable document so a
        # filename-only match still surfaces the chunk. concat_ws tolerates NULLs.
        document = func.concat_ws(" ", DocumentChunk.content, Document.file_name)
        tsvector = func.to_tsvector(_TS_CONFIG, document)
        tsquery = func.websearch_to_tsquery(_TS_CONFIG, query)
        rank_score = func.ts_rank(tsvector, tsquery)

        stmt = (
            select(DocumentChunk.id, rank_score.label("score"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.deleted_at.is_(None))
            .where(tsvector.op("@@")(tsquery))
            .order_by(rank_score.desc(), DocumentChunk.id.asc())
            .limit(limit)
        )
        stmt = self._apply_owner_filter(stmt, owner_id)

        result = await self._session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    async def _search_like(
        self,
        *,
        terms: list[str],
        owner_id: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        """
        SQLite/offline fallback: parameterised term-overlap LIKE search.

        Each term is matched (case-insensitively) against chunk content and
        document filename. The relevance score is the number of distinct terms
        that matched, so chunks hitting more query terms rank higher.
        """
        per_term_conditions: list[ColumnElement[bool]] = []
        score_terms: list[ColumnElement[int]] = []
        for term in terms:
            # `term` is a tokenised alphanumeric word; the pattern value is
            # bound as a parameter by SQLAlchemy (never concatenated into SQL).
            pattern = f"%{term}%"
            matched = or_(
                DocumentChunk.content.ilike(pattern),
                Document.file_name.ilike(pattern),
            )
            per_term_conditions.append(matched)
            score_terms.append(case((matched, 1), else_=0))

        score_expr = reduce(lambda a, b: a + b, score_terms).cast(Integer).label("score")

        stmt = (
            select(DocumentChunk.id, score_expr)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.deleted_at.is_(None))
            .where(or_(*per_term_conditions))
            .order_by(score_expr.desc(), DocumentChunk.id.asc())
            .limit(limit)
        )
        stmt = self._apply_owner_filter(stmt, owner_id)

        result = await self._session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_owner_filter(stmt, owner_id: uuid.UUID | None):  # type: ignore[no-untyped-def]
        """Apply the Layer-1 ownership filter in SQL when owner_id is set."""
        if owner_id is not None:
            stmt = stmt.where(Document.owner_id == owner_id)
        return stmt

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Lowercase, extract alphanumeric terms, dedupe, and bound the count."""
        seen: list[str] = []
        for token in _TOKEN_RE.findall(text.lower()):
            if token not in seen:
                seen.append(token)
            if len(seen) >= _MAX_QUERY_TERMS:
                break
        return seen

    def _dialect_name(self) -> str:
        """
        Return the bound dialect name ("postgresql", "sqlite", ...).

        Defaults to postgresql when the bind cannot be determined so production
        never silently degrades to the LIKE fallback.
        """
        bind = self._session.bind
        if bind is None:
            return "postgresql"
        return bind.dialect.name
