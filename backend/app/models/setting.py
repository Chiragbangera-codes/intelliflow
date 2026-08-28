"""
Setting ORM model.

Stores application-level configuration key/value pairs.

SECURITY: This table must NEVER be used to store passwords, JWT secrets,
API keys, or any sensitive credentials. Those belong in environment
variables and the Settings class (app/core/config.py), not here.

This table is for user-facing configuration only (company name, theme,
language, timezone, non-sensitive email metadata, etc.).

Fields per DATABASE_SCHEMA.md §5 (settings):
  key (unique), value, description, is_public
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Setting(Base):
    """
    Application configuration key/value entry.

    SECURITY: Must NEVER be used for secrets, passwords, JWT secrets,
    or API keys. Those belong in environment variables / Settings config.
    """

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("key", name="uq_settings_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        doc=(
            "Setting identifier (e.g. 'company_name', 'theme', 'timezone'). "
            "Never use for secrets or credentials."
        ),
    )
    value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc=(
            "Setting value as a plain string. "
            "Never store passwords, API keys, or JWT secrets here."
        ),
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable description of what this setting controls.",
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        doc="True if this setting may be returned to authenticated non-admin users.",
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

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} is_public={self.is_public}>"
