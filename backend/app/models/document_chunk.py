"""
DocumentChunk ORM model.

Stores text chunks extracted from documents for AI retrieval (RAG).
There is NO embedding_id here — the relationship is:

    documents
        ↓
    document_chunks
        ↓  (via ai_embeddings.document_chunk_id)
    ai_embeddings

Vectors are stored in FAISS. Only text content and ordering metadata
are kept here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ai_embedding import AIEmbedding
    from app.models.document import Document


class DocumentChunk(Base):
    """A single ordered text chunk of a document used for RAG retrieval."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        # Prevent duplicate chunk numbers within the same document.
        UniqueConstraint(
            "document_id",
            "chunk_number",
            name="uq_document_chunks_doc_chunk",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent document. Chunk is deleted when the document is physically deleted.",
    )
    chunk_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Zero-based sequential chunk index within the document.",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Raw extracted text content of this chunk.",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
        lazy="selectin",
    )
    embedding: Mapped[AIEmbedding | None] = relationship(
        "AIEmbedding",
        back_populates="chunk",
        uselist=False,
        lazy="raise",
        doc="Embedding metadata for this chunk. Loaded explicitly when needed.",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk id={self.id}"
            f" document_id={self.document_id}"
            f" chunk={self.chunk_number}>"
        )
