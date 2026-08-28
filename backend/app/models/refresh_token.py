"""
RefreshToken ORM model.

Stores the SHA-256 hash of issued refresh tokens for server-side revocation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """Server-side record of an issued refresh token (stored as SHA-256 hash)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="The user this token belongs to.",
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 hex digest = exactly 64 characters
        nullable=False,
        unique=True,
        index=True,
        doc="SHA-256 hex digest of the raw refresh token sent to the client.",
    )
    expires_at: Mapped[datetime] = mapped_column(
        nullable=False,
        doc="UTC expiry timestamp. Token is invalid after this point.",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="UTC revocation timestamp. NULL means the token has not been revoked.",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped[User] = relationship(
        "User",
        back_populates="refresh_tokens",
    )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def is_valid(self) -> bool:
        """
        Return True if the token is still usable.

        A token is valid when:
          1. It has not been explicitly revoked.
          2. Its expiry time has not passed.
        """
        now = datetime.now(UTC)
        expires = (
            self.expires_at
            if self.expires_at.tzinfo is not None
            else self.expires_at.replace(tzinfo=UTC)
        )
        return self.revoked_at is None and expires > now

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} " f"valid={self.is_valid}>"
