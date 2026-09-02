"""
Event and Transactional Outbox ORM models.

Provides:
  - Event: Normalized platform event record for auditing, telemetry, and external consumers.
  - OutboxEvent: Transactional outbox table for guaranteed atomic event publishing.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class EventStatus(str, enum.Enum):
    """Lifecycle status of events and outbox messages."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class Event(Base):
    """
    Normalized platform event record.
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Normalized event identifier (e.g. 'document.created', 'workflow.completed').",
    )
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="intelliflow.core",
        index=True,
        doc="Subsystem that produced the event.",
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who triggered the event. Null for system-generated events.",
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        doc="Entity type affected (e.g. 'document', 'workflow', 'report').",
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        doc="Identifier of the affected entity.",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Event payload data (JSON/JSONB).",
    )
    correlation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4()),
        doc="Distributed tracing / correlation ID.",
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            name="event_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EventStatus.PROCESSED,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Failure details if event processing encountered an error.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    actor: Mapped[User | None] = relationship(
        "User",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Event id={self.id} type={self.event_type!r} correlation_id={self.correlation_id!r}>"
        )


class OutboxEvent(Base):
    """
    Transactional Outbox record.
    Written in the same database transaction as the business entity update.
    Drained asynchronously by the worker outbox processor.
    """

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="intelliflow.core",
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            name="event_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EventStatus.PENDING,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<OutboxEvent id={self.id} type={self.event_type!r} "
            f"status={self.status.value} retries={self.retry_count}>"
        )
