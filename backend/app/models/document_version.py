"""
DocumentVersion ORM model — Milestone 11.

Stores historical and current versions of documents.
Preserves immutability of historical file versions and allows non-destructive
version restoration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk
    from app.models.user import User


class DocumentVersion(Base):
    """Specific revision/version of an uploaded document."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_doc_ver",
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
        doc="Parent document reference.",
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Sequential version number (1, 2, 3...).",
    )
    file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Filename associated with this version.",
    )
    storage_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        doc="Physical object storage path for this specific version.",
    )
    file_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="MIME type.",
    )
    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        doc="File size in bytes.",
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hex digest.",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="User who uploaded/created this version.",
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
        doc="True if this is the active/current version of the document.",
    )
    change_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional note describing the change in this version.",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="versions",
        lazy="selectin",
    )
    creator: Mapped[User] = relationship(
        "User",
        lazy="selectin",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentVersion id={self.id} doc={self.document_id} "
            f"v={self.version_number} current={self.is_current}>"
        )
