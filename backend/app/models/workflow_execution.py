"""
WorkflowExecution ORM model.

Records historical workflow execution runs.
Does not implement the execution engine.

Fields per DATABASE_SCHEMA.md §5 (workflow_executions):
  workflow_id, status, duration, logs
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workflow import Workflow


class ExecutionStatus(str, enum.Enum):
    """Status of a workflow execution run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowExecution(Base):
    """Historical record of a single workflow execution run."""

    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="The workflow definition that was executed.",
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who triggered the execution. NULL for system-triggered runs.",
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(
            ExecutionStatus,
            name="execution_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=ExecutionStatus.PENDING,
        server_default="pending",
    )
    duration: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Total wall-clock execution time in seconds.",
    )
    logs: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Structured execution log entries as JSON (JSONB in PostgreSQL).",
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
    workflow: Mapped[Workflow] = relationship(
        "Workflow",
        back_populates="executions",
        lazy="selectin",
    )
    triggered_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[triggered_by],
        back_populates="workflow_executions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowExecution id={self.id}"
            f" workflow_id={self.workflow_id}"
            f" status={self.status.value}>"
        )
