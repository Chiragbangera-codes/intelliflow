"""
Webhook and WebhookDelivery ORM models.

Provides:
  - Webhook: Webhook subscriber endpoint configuration with HMAC secret and subscribed events.
  - WebhookDelivery: Audit log of every webhook dispatch attempt with status, duration, and response codes.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class WebhookDeliveryStatus(str, enum.Enum):
    """Delivery status of a webhook dispatch attempt."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class Webhook(Base):
    """
    Enterprise Webhook registration.
    """

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        doc="Destination HTTP/HTTPS endpoint URL.",
    )
    secret: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Encrypted or hashed secret used for HMAC-SHA256 signature.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )
    subscribed_events: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["*"],
        doc="List of subscribed event types (e.g. ['document.created', 'workflow.completed']) or ['*'] for all.",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    creator: Mapped[User | None] = relationship("User", lazy="selectin")
    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        "WebhookDelivery",
        back_populates="webhook",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Webhook id={self.id} name={self.name!r} url={self.url!r} active={self.is_active}>"


class WebhookDelivery(Base):
    """
    Audit and diagnostic log for a webhook delivery attempt.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    request_headers: Mapped[dict[str, str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    response_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    response_body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    response_headers: Mapped[dict[str, str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(
            WebhookDeliveryStatus,
            name="webhook_delivery_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    error_message: Mapped[str | None] = mapped_column(
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
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    webhook: Mapped[Webhook] = relationship("Webhook", back_populates="deliveries")

    def __repr__(self) -> str:
        return (
            f"<WebhookDelivery id={self.id} webhook_id={self.webhook_id} "
            f"event_type={self.event_type!r} status={self.status.value}>"
        )
