"""
SearchRepository — PostgreSQL resolution of FAISS chunk IDs.

Responsibilities:
  - Accept a list of chunk UUIDs returned by FAISS.
  - Resolve them to (DocumentChunk + Document) metadata in ONE batched query.
  - Optionally filter by document owner_id for non-admin RBAC enforcement.
  - Exclude soft-deleted documents automatically.
  - Return results keyed by chunk_id for O(1) lookup in the service layer.

Performance:
  - Uses a single SQL SELECT with an IN clause rather than one query per chunk.
  - This eliminates the N+1 pattern that would result from resolving each
    FAISS result individually.

Note: The SQL owner_id filter is one layer of RBAC.  The service applies a
second, in-process ownership check for defence-in-depth.  Neither layer
alone is sufficient.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk

# ---------------------------------------------------------------------------
# Result dataclass — carries all fields the service / schema needs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkWithDocument:
    """Resolved chunk + document metadata returned from a batched DB query."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_owner_id: uuid.UUID  # used by service for defence-in-depth check
    document_name: str
    chunk_number: int
    content: str
    file_type: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class SearchRepository:
    """
    Resolves FAISS chunk IDs to full chunk + document metadata.

    A single batched PostgreSQL query is issued regardless of how many
    chunk IDs are provided.  The query joins document_chunks with documents
    and optionally restricts to a single owner.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._session = db

    async def get_chunks_with_documents(
        self,
        chunk_ids: list[uuid.UUID],
        *,
        owner_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, ChunkWithDocument]:
        """
        Fetch chunk + document metadata for a list of chunk UUIDs.

        This is intentionally a SINGLE SQL query (IN clause) to avoid the
        N+1 problem where each FAISS result would otherwise require its own
        round-trip to PostgreSQL.

        Args:
            chunk_ids: Chunk UUIDs returned by FAISS.  May contain stale IDs.
            owner_id:  If supplied, restricts results to documents owned by
                       this user (employee / manager access).  If None, all
                       non-deleted documents are eligible (admin / hr access).

        Returns:
            Dict mapping chunk_id → ChunkWithDocument for found, authorized,
            non-deleted chunks.  Stale or inaccessible chunk IDs are simply
            absent from the dict — they are never an error.
        """
        if not chunk_ids:
            return {}

        # -------------------------------------------------------------------
        # Single batched query:
        #   SELECT dc.id, dc.document_id, dc.chunk_number, dc.content,
        #          dc.created_at, d.file_name, d.owner_id, d.file_type
        #   FROM document_chunks dc
        #   JOIN documents d ON dc.document_id = d.id
        #   WHERE dc.id IN (:chunk_ids)
        #     AND d.deleted_at IS NULL
        #     [AND d.owner_id = :owner_id]   -- only for non-admin users
        # -------------------------------------------------------------------
        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.chunk_number,
                DocumentChunk.content,
                DocumentChunk.created_at,
                Document.file_name,
                Document.owner_id,
                Document.file_type,
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                DocumentChunk.id.in_(chunk_ids),
                Document.deleted_at.is_(None),
            )
        )

        if owner_id is not None:
            # First RBAC layer: SQL-level owner filter
            stmt = stmt.where(Document.owner_id == owner_id)

        result = await self._session.execute(stmt)
        rows = result.fetchall()

        resolved: dict[uuid.UUID, ChunkWithDocument] = {}
        for row in rows:
            cid = row[0]
            resolved[cid] = ChunkWithDocument(
                chunk_id=cid,
                document_id=row[1],
                chunk_number=row[2],
                content=row[3],
                created_at=row[4],
                document_name=row[5],
                document_owner_id=row[6],
                file_type=row[7],
            )

        return resolved
