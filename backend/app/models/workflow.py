"""
Workflow ORM model.

Stores workflow definitions.
Execution logic is implemented in a later milestone (Milestone 8).

Fields per DATABASE_SCHEMA.md §5 (workflows):
  name, description, created_by, active, version
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workflow_execution import WorkflowExecution
    from app.models.workflow_step import WorkflowStep


class Workflow(Base):
    """Definition of an automated workflow."""

    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Human-readable workflow name.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who created this workflow. SET NULL if the user is deleted.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="Whether this workflow can be triggered.",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        doc="Schema version of the workflow definition.",
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Soft-delete timestamp. NULL means the record is active.",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    creator: Mapped[User | None] = relationship(
        "User",
        back_populates="workflows",
        lazy="selectin",
        doc="The user who defined this workflow.",
    )
    steps: Mapped[list[WorkflowStep]] = relationship(
        "WorkflowStep",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="WorkflowStep.step_number",
        doc="Ordered steps of the workflow. Load explicitly when needed.",
    )
    executions: Mapped[list[WorkflowExecution]] = relationship(
        "WorkflowExecution",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="raise",
        doc="Historical execution runs. Load explicitly when needed.",
    )

    def __repr__(self) -> str:
        return f"<Workflow id={self.id} name={self.name!r} active={self.is_active}>"
