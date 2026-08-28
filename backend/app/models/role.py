"""
Role ORM model.

Defines the system roles used for Role-Based Access Control (RBAC).
Roles are seeded by the 001_auth migration and are not user-manageable
in Milestone 2.

Default roles (seeded):
  - admin    — full system access
  - manager  — elevated permissions
  - employee — default for new registrations
  - hr       — human resources access
  - finance  — finance department access
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Role(Base):
    """System role definition used for RBAC."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique role identifier (e.g. 'admin', 'employee').",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of the role's purpose.",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"
