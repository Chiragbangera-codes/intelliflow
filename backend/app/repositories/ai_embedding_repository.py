"""
AIEmbedding repository.

Provides database operations for the ai_embeddings table:
  - Create embedding metadata record
  - Retrieve by chunk ID
  - Bulk-delete by document ID (for document deletion cascades)
  - Fetch all embeddings with their associated chunks (for FAISS rebuild)

The actual float vectors are stored in FAISS.
Only metadata (model name, FAISS row reference) is stored in PostgreSQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ai_embedding import AIEmbedding
from app.models.document_chunk import DocumentChunk


class AIEmbeddingRepository:
    """Encapsulates database access for the ai_embeddings table."""

    def __init__(self, db: AsyncSession) -> None:
        self._session = db

    async def create(
        self,
        document_chunk_id: uuid.UUID,
        vector_reference: str,
        embedding_model: str,
    ) -> AIEmbedding:
        """
        Create an AIEmbedding metadata record.

        Args:
            document_chunk_id: The UUID of the associated DocumentChunk.
            vector_reference:  Key identifying the vector in FAISS (e.g. the
                               FAISS row integer as a string).
            embedding_model:   Model name/version used to produce the vector.

        Returns:
            The newly created (unflushed) AIEmbedding ORM instance.
        """
        embedding = AIEmbedding(
            document_chunk_id=document_chunk_id,
            vector_reference=vector_reference,
            embedding_model=embedding_model,
        )
        self._session.add(embedding)
        await self._session.flush()
        return embedding

    async def get_by_chunk_id(
        self,
        chunk_id: uuid.UUID,
    ) -> AIEmbedding | None:
        """
        Return the AIEmbedding for a specific chunk, or None if not found.

        Args:
            chunk_id: UUID of the DocumentChunk to look up.
        """
        stmt = select(AIEmbedding).where(AIEmbedding.document_chunk_id == chunk_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_document_id(
        self,
        document_id: uuid.UUID,
    ) -> int:
        """
        Bulk-delete all AIEmbedding records whose chunks belong to a document.

        Used when a document is deleted so orphan embedding metadata is removed.
        The FAISS index must be rebuilt separately after calling this method.

        Args:
            document_id: UUID of the parent Document.

        Returns:
            Number of rows deleted.
        """
        # Sub-select: get chunk IDs for the given document
        chunk_ids_stmt = select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
        chunk_ids_result = await self._session.execute(chunk_ids_stmt)
        chunk_ids = [row[0] for row in chunk_ids_result.fetchall()]

        if not chunk_ids:
            return 0

        stmt = delete(AIEmbedding).where(AIEmbedding.document_chunk_id.in_(chunk_ids))
        result = await self._session.execute(stmt)
        return result.rowcount

    async def get_all_with_chunks(self) -> Sequence[AIEmbedding]:
        """
        Fetch all AIEmbedding rows with their associated DocumentChunk eagerly loaded.

        Used during worker warm-up to rebuild the FAISS index from persisted
        embedding metadata and chunk content.

        Returns:
            Sequence of AIEmbedding instances ordered by creation time.
        """
        stmt = (
            select(AIEmbedding)
            .options(selectinload(AIEmbedding.chunk))
            .order_by(AIEmbedding.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
