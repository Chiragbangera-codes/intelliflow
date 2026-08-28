"""
Notification ORM model.

Stores notification records for users.
Does not implement notification delivery.

Fields per DATABASE_SCHEMA.md §5 (notifications):
  user_id, title, message, channel, is_read, priority, sent_at
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class NotificationChannel(str, enum.Enum):
    """Delivery channel for a notification."""

    EMAIL = "email"
    IN_APP = "in_app"
    SMS = "sms"


class NotificationPriority(str, enum.Enum):
    """Priority level of a notification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Notification(Base):
    """Notification record for a specific user."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Recipient user. Notification is deleted when the user is deleted.",
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(
            NotificationChannel,
            name="notification_channel",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=NotificationChannel.IN_APP,
        server_default="in_app",
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
        doc="True once the user has acknowledged the notification.",
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        SAEnum(
            NotificationPriority,
            name="notification_priority",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=NotificationPriority.MEDIUM,
        server_default="medium",
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="UTC timestamp when the notification was delivered. NULL if pending.",
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
    user: Mapped[User] = relationship(
        "User",
        back_populates="notifications",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id}" f" user_id={self.user_id}" f" is_read={self.is_read}>"
