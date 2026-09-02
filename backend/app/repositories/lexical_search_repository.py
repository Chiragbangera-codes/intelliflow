"""
LexicalSearchRepository — keyword/full-text retrieval over document chunks with Milestone 11 lifecycle filtering.

This is the lexical half of hybrid retrieval (the semantic half lives in
VectorStoreService + SearchService). It finds chunks whose *text* matches the
query terms, complementing the semantic branch which finds chunks whose
*meaning* is close. Fusing the two (see HybridSearchService) recovers exact
keyword / filename / rare-token matches that pure vector search often misses.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from functools import reduce

from sqlalchemy import ColumnElement, Integer, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentLifecycleStatus
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_MAX_QUERY_TERMS = 32
_TS_CONFIG = "simple"


@dataclass(frozen=True)
class LexicalMatch:
    """One lexical retrieval candidate."""

    chunk_id: uuid.UUID
    rank: int
    score: float


class LexicalSearchRepository:
    """Keyword/full-text search over non-deleted, active document chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        query: str,
        owner_id: uuid.UUID | None,
        limit: int,
    ) -> list[LexicalMatch]:
        """Return the top lexical matches for query, ranked best-first."""
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
        """Document-aware lookup returning leading chunks of matching documents."""
        if not terms or chunks_per_doc < 1 or max_docs < 1:
            return []

        terms = terms[:_MAX_QUERY_TERMS]

        match_conditions: list[ColumnElement[bool]] = []
        score_terms: list[ColumnElement[int]] = []
        for term in terms:
            pattern = f"%{term}%"
            cond = or_(Document.file_name.ilike(pattern), Document.title.ilike(pattern))
            match_conditions.append(cond)
            score_terms.append(case((cond, 1), else_=0))
        score_expr = reduce(lambda a, b: a + b, score_terms).cast(Integer)

        doc_query = select(Document.id.label("doc_id"), score_expr.label("match_score")).where(
            Document.deleted_at.is_(None),
            Document.lifecycle_status == DocumentLifecycleStatus.ACTIVE,
            or_(*match_conditions),
        )
        doc_query = self._apply_owner_filter(doc_query, owner_id)
        matched_docs = (
            doc_query.order_by(score_expr.desc(), Document.id.asc()).limit(max_docs).subquery()
        )

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

    async def _search_postgres(
        self,
        *,
        query: str,
        owner_id: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        """PostgreSQL full-text search over chunk content + document filename/title."""
        document = func.concat_ws(" ", DocumentChunk.content, Document.file_name, Document.title)
        tsvector = func.to_tsvector(_TS_CONFIG, document)
        tsquery = func.websearch_to_tsquery(_TS_CONFIG, query)
        rank_score = func.ts_rank(tsvector, tsquery)

        stmt = (
            select(DocumentChunk.id, rank_score.label("score"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.deleted_at.is_(None),
                Document.lifecycle_status == DocumentLifecycleStatus.ACTIVE,
                tsvector.op("@@")(tsquery),
            )
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
        """SQLite/offline fallback: parameterised term-overlap LIKE search."""
        per_term_conditions: list[ColumnElement[bool]] = []
        score_terms: list[ColumnElement[int]] = []
        for term in terms:
            pattern = f"%{term}%"
            matched = or_(
                DocumentChunk.content.ilike(pattern),
                Document.file_name.ilike(pattern),
                Document.title.ilike(pattern),
            )
            per_term_conditions.append(matched)
            score_terms.append(case((matched, 1), else_=0))

        score_expr = reduce(lambda a, b: a + b, score_terms).cast(Integer).label("score")

        stmt = (
            select(DocumentChunk.id, score_expr)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.deleted_at.is_(None),
                Document.lifecycle_status == DocumentLifecycleStatus.ACTIVE,
                or_(*per_term_conditions),
            )
            .order_by(score_expr.desc(), DocumentChunk.id.asc())
            .limit(limit)
        )
        stmt = self._apply_owner_filter(stmt, owner_id)

        result = await self._session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    @staticmethod
    def _apply_owner_filter(stmt, owner_id: uuid.UUID | None):  # type: ignore[no-untyped-def]
        if owner_id is not None:
            stmt = stmt.where(Document.owner_id == owner_id)
        return stmt

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        seen: list[str] = []
        for token in _TOKEN_RE.findall(text.lower()):
            if token not in seen:
                seen.append(token)
            if len(seen) >= _MAX_QUERY_TERMS:
                break
        return seen

    def _dialect_name(self) -> str:
        bind = self._session.bind
        if bind is None:
            return "postgresql"
        return bind.dialect.name
