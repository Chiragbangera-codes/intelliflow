"""
AIEmbedding ORM model.

Stores embedding metadata for document chunks.
Actual vectors are stored in FAISS — not in PostgreSQL.

Relationship (one-to-one):
    document_chunks 1──1 ai_embeddings

The FK direction is: ai_embeddings.document_chunk_id → document_chunks.id
There is no circular FK relationship.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk


class AIEmbedding(Base):
    """Embedding metadata for a document chunk. Vectors live in FAISS."""

    __tablename__ = "ai_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    document_chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        doc="One-to-one FK to document_chunks. Embedding is deleted with the chunk.",
    )
    vector_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Key or ID used to locate the vector in FAISS index.",
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        doc="Name/version of the embedding model (e.g. 'sentence-transformers/all-MiniLM-L6-v2').",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    chunk: Mapped[DocumentChunk] = relationship(
        "DocumentChunk",
        back_populates="embedding",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AIEmbedding id={self.id} chunk_id={self.document_chunk_id}>"
