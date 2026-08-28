"""
DocumentChunk repository.

Provides database operations for document text chunks:
  - Fetch ordered chunks for a document
  - Save newly extracted chunks (replacing any previous chunks on rerun)
  - Delete chunks for a document
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk


class DocumentChunkRepository:
    """Encapsulates database access for the document_chunks table."""

    def __init__(self, db: AsyncSession) -> None:
        self._session = db

    async def get_chunks_by_document(
        self,
        document_id: uuid.UUID,
    ) -> Sequence[DocumentChunk]:
        """Return all text chunks for a document ordered by chunk_number ascending."""
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_number.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def delete_chunks_by_document(
        self,
        document_id: uuid.UUID,
    ) -> None:
        """Delete all existing text chunks for a given document."""
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        await self._session.execute(stmt)

    async def save_chunks(
        self,
        document_id: uuid.UUID,
        chunks: list[str],
    ) -> list[DocumentChunk]:
        """
        Atomically delete old chunks and persist the new ordered text chunks.

        Chunk numbers are 1-based sequential integers: 1, 2, 3, ...
        """
        # Delete previous chunks to guarantee idempotence and prevent duplicates
        await self.delete_chunks_by_document(document_id)

        chunk_records: list[DocumentChunk] = []
        for index, text in enumerate(chunks, start=1):
            chunk = DocumentChunk(
                document_id=document_id,
                chunk_number=index,
                content=text,
            )
            self._session.add(chunk)
            chunk_records.append(chunk)

        await self._session.flush()
        return chunk_records
