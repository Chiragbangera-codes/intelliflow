"""
Department ORM model.

Stores organisational department definitions.
Users are assigned to departments via users.department_id (nullable FK).

Soft-delete is supported; physical deletion is blocked by ON DELETE RESTRICT
on users.department_id so departments with active users cannot be removed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Department(Base):
    """Organisational department — parent of users."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        doc="UUID primary key.",
    )
    name: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        doc="Department name — unique across the organisation.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Soft-delete timestamp. NULL means the record is active.",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    users: Mapped[list[User]] = relationship(
        "User",
        back_populates="department",
        lazy="raise",
        doc="Users assigned to this department. Never eager-loaded.",
    )

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name!r}>"
