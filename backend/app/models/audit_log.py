"""
AuditLog ORM model.

Immutable record of important application events.

Design notes:
  - record_id is a plain UUID column WITHOUT a foreign key constraint.
    Audit logs can reference records from any table; a FK would make
    this impossible and would risk cascade-deleting audit history.
  - user_id uses SET NULL so audit records survive user deletion.
  - old_value / new_value are JSON (JSONB in PostgreSQL migration).
  - This table should be append-only at the application level.

Fields per DATABASE_SCHEMA.md §5 (audit_logs):
  user_id, action, table_name, record_id, old_value, new_value,
  ip_address, created_at
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """Immutable audit trail entry for an application event."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who performed the action. NULL for system-initiated events.",
    )
    action: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Short action descriptor (e.g. 'user.login', 'document.delete').",
    )
    table_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Database table the action affected.",
    )
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        # Intentionally NO ForeignKey — record_id can point to any table.
        nullable=True,
        doc=(
            "UUID of the affected record. No FK constraint — audit logs "
            "may reference records across different tables."
        ),
    )
    old_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Previous state of the record as JSON (JSONB in PostgreSQL).",
    )
    new_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="New state of the record as JSON (JSONB in PostgreSQL).",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        doc="IPv4 or IPv6 address of the request (max 45 chars covers full IPv6).",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
        doc="UTC timestamp of the event.",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped[User | None] = relationship(
        "User",
        back_populates="audit_logs",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id}" f" action={self.action!r}" f" user_id={self.user_id}>"
