"""
Document ORM model.

Stores metadata for uploaded documents.
The actual file is NEVER stored in PostgreSQL — only the storage path,
checksums, and processing state are kept here.

Enums:
  DocumentStatus — tracks the overall pipeline state of the document.
  OcrStatus      — tracks the OCR processing state independently.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.user import User


class DocumentStatus(str, enum.Enum):
    """Overall processing status of a document."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class OcrStatus(str, enum.Enum):
    """OCR processing status of a document."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Document(Base):
    """Uploaded document metadata — file content is never stored here."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        doc="Original file name as uploaded.",
    )
    storage_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        doc="Key/path in object storage. The file itself is not in PostgreSQL.",
    )
    file_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="MIME type (e.g. 'application/pdf', 'image/png').",
    )
    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        doc="File size in bytes.",
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="User who owns / uploaded this document.",
    )
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=DocumentStatus.PENDING,
        server_default="pending",
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hex digest of the file for integrity verification.",
    )
    ocr_status: Mapped[OcrStatus] = mapped_column(
        SAEnum(OcrStatus, name="ocr_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=OcrStatus.PENDING,
        server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
        doc="Upload/creation timestamp (UTC).",
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Soft-delete timestamp. NULL means the record is active.",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    owner: Mapped[User] = relationship(
        "User",
        back_populates="documents",
        lazy="selectin",
        doc="The user who uploaded this document.",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="DocumentChunk.chunk_number",
        doc="Text chunks derived from this document. Never eager-loaded.",
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} file_name={self.file_name!r}" f" status={self.status.value}>"
        )
