"""
Integration ORM model.

Supports external system connections (Webhook, Slack, MS Teams, Email, Generic HTTP)
with encrypted credentials at rest.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class IntegrationProvider(str, enum.Enum):
    """Supported external integration providers."""

    WEBHOOK = "webhook"
    SLACK = "slack"
    MSTEAMS = "msteams"
    EMAIL = "email"
    GENERIC_HTTP = "generic_http"


class IntegrationStatus(str, enum.Enum):
    """Health and operational status of an integration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Integration(Base):
    """
    Configured external integration endpoint with encrypted secrets.
    """

    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(
            IntegrationProvider,
            name="integration_provider",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(
            IntegrationStatus,
            name="integration_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=IntegrationStatus.ACTIVE,
        index=True,
    )
    encrypted_credentials: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="AES/Fernet encrypted credentials (API keys, webhook tokens, passwords).",
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Non-secret provider settings (channel, recipient list, endpoint URL template, headers).",
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
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    creator: Mapped[User | None] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Integration id={self.id} name={self.name!r} provider={self.provider.value} status={self.status.value}>"
