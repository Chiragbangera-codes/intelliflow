"""
DocumentChunk ORM model — Milestone 11.

Stores text chunks extracted from documents for AI retrieval (RAG).
Version-aware: chunks are associated with a specific DocumentVersion.
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
    from app.models.document_version import DocumentVersion


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
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="Document version this chunk was extracted from.",
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        doc="Version number corresponding to this chunk.",
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
    version: Mapped[DocumentVersion | None] = relationship(
        "DocumentVersion",
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
            f" v={self.version_number}"
            f" chunk={self.chunk_number}>"
        )
