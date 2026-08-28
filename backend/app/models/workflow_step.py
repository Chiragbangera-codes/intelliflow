"""
WorkflowStep ORM model.

Defines ordered steps within a workflow definition.
Does not implement step execution logic.

Fields per DATABASE_SCHEMA.md §5 (workflow_steps):
  workflow_id, step_number, action, configuration, timeout, retry_count
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.workflow import Workflow


class WorkflowStep(Base):
    """A single ordered step in a workflow definition."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        # Each step number must be unique within a workflow.
        UniqueConstraint(
            "workflow_id",
            "step_number",
            name="uq_workflow_steps_wf_step",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent workflow. Step is deleted when the workflow is physically deleted.",
    )
    step_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="1-based sequential position of this step within the workflow.",
    )
    action: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Action identifier (e.g. 'ocr', 'send_email', 'archive').",
    )
    configuration: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Step-specific configuration as JSON (JSONB in PostgreSQL).",
    )
    timeout: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Maximum execution time in seconds before the step is aborted.",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Number of retry attempts on failure. 0 means no retries.",
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
        back_populates="steps",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowStep id={self.id}"
            f" workflow_id={self.workflow_id}"
            f" step={self.step_number}>"
        )
