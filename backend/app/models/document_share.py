"""
DocumentShare ORM model — Milestone 11.

Stores granular user-level document sharing access grants with configurable
permissions ('view', 'download', 'edit', 'manage') and optional expiration.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class DocumentSharePermission(str, enum.Enum):
    """Permissions granted by a document share."""

    VIEW = "view"
    DOWNLOAD = "download"
    EDIT = "edit"
    MANAGE = "manage"


class DocumentShare(Base):
    """Access grant allowing a specific user access to a document."""

    __tablename__ = "document_shares"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "user_id",
            name="uq_document_shares_doc_user",
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
        doc="Shared document reference.",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Grantee user receiving access.",
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        doc="User who created/granted this share.",
    )
    permission: Mapped[DocumentSharePermission] = mapped_column(
        SAEnum(
            DocumentSharePermission,
            name="document_share_permission",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=DocumentSharePermission.VIEW,
        server_default="view",
        doc="Granted permission level.",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        index=True,
        doc="Optional expiration timestamp. NULL means never expires.",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        index=True,
        doc="Timestamp when access was revoked. NULL means active grant.",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="shares",
        lazy="selectin",
    )
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="selectin",
    )
    grantor: Mapped[User] = relationship(
        "User",
        foreign_keys=[granted_by],
        lazy="selectin",
    )

    @property
    def is_active(self) -> bool:
        """Check if grant is currently active (not revoked and not expired)."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            exp = self.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp <= datetime.now(UTC):
                return False
        return True

    def __repr__(self) -> str:
        return (
            f"<DocumentShare id={self.id} doc={self.document_id} "
            f"user={self.user_id} perm={self.permission.value} active={self.is_active}>"
        )
