"""
Automation Rule and Execution ORM models.

Provides:
  - AutomationRule: Configurable event-driven rule with conditions and actions.
  - AutomationExecution: Execution audit log with action status and latency metrics.
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


class AutomationStatus(str, enum.Enum):
    """Execution status of an automation rule run."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class AutomationRule(Base):
    """
    Event-driven automation rule.
    Triggered when an event matching `trigger_event` is published and its conditions evaluate to True.
    """

    __tablename__ = "automation_rules"

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
    trigger_event: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        doc="Event type that triggers this rule (e.g. 'document.created', 'security.alert', '*').",
    )
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="List of condition objects: [{'field': 'payload.confidentiality', 'operator': 'equals', 'value': 'restricted'}].",
    )
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="List of action objects: [{'type': 'send_notification', 'config': {...}}, {'type': 'send_webhook', 'config': {...}}].",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
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

    # Relationships
    creator: Mapped[User | None] = relationship("User", lazy="selectin")
    executions: Mapped[list[AutomationExecution]] = relationship(
        "AutomationExecution",
        back_populates="rule",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<AutomationRule id={self.id} name={self.name!r} trigger={self.trigger_event!r} active={self.is_active}>"


class AutomationExecution(Base):
    """
    Audit log of an automation rule execution.
    """

    __tablename__ = "automation_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
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
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(
            AutomationStatus,
            name="automation_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=AutomationStatus.SUCCESS,
        index=True,
    )
    action_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="Summary results of each action executed.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    execution_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    rule: Mapped[AutomationRule] = relationship("AutomationRule", back_populates="executions")

    def __repr__(self) -> str:
        return (
            f"<AutomationExecution id={self.id} rule_id={self.rule_id} "
            f"status={self.status.value}>"
        )
