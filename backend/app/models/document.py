"""
Document ORM model — Milestone 11.

Stores metadata for uploaded documents, enterprise classifications, lifecycle states,
and associations to departments, versions, chunks, and access grants.
The actual file is NEVER stored in PostgreSQL — only the storage path,
checksums, and processing state are kept here.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.document_chunk import DocumentChunk
    from app.models.document_share import DocumentShare
    from app.models.document_version import DocumentVersion
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


class DocumentLifecycleStatus(str, enum.Enum):
    """Enterprise lifecycle status of a document."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPIRED = "expired"
    DELETED = "deleted"


class DocumentConfidentiality(str, enum.Enum):
    """Confidentiality classification."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


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
    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
        doc="Human-friendly display title for the document.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Detailed document summary or description.",
    )
    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Document category (e.g. contract, invoice, policy, report).",
    )
    document_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Functional classification (e.g. financial, legal, technical, hr).",
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default="[]",
        doc="List of custom search tags.",
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
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Department association for departmental RBAC access.",
    )
    confidentiality: Mapped[DocumentConfidentiality] = mapped_column(
        SAEnum(
            DocumentConfidentiality,
            name="document_confidentiality",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=DocumentConfidentiality.INTERNAL,
        server_default="internal",
        index=True,
        doc="Confidentiality classification level.",
    )
    lifecycle_status: Mapped[DocumentLifecycleStatus] = mapped_column(
        SAEnum(
            DocumentLifecycleStatus,
            name="document_lifecycle_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=DocumentLifecycleStatus.ACTIVE,
        server_default="active",
        index=True,
        doc="Enterprise lifecycle state.",
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
    ocr_status: Mapped[OcrStatus] = mapped_column(
        SAEnum(OcrStatus, name="ocr_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=OcrStatus.PENDING,
        server_default="pending",
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hex digest of current version for integrity verification.",
    )
    retention_period_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Retention period in days from creation.",
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when document transitioned to active.",
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when document transitioned to archived.",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        index=True,
        doc="Optional expiration date after which the document is expired.",
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
    department: Mapped[Department | None] = relationship(
        "Department",
        lazy="selectin",
        doc="Department assigned to this document.",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="DocumentChunk.chunk_number",
        doc="Text chunks derived from this document.",
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DocumentVersion.version_number.desc()",
        doc="Revision history for this document.",
    )
    shares: Mapped[list[DocumentShare]] = relationship(
        "DocumentShare",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        doc="Access grants for this document.",
    )

    @property
    def display_name(self) -> str:
        """Return title if available, otherwise file_name."""
        return self.title or self.file_name

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} file_name={self.file_name!r}"
            f" status={self.status.value} lifecycle={self.lifecycle_status.value}>"
        )
