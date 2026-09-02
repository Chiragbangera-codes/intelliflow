"""
Report ORM model.

Stores generated report metadata.
Does not implement report generation logic.

Fields per DATABASE_SCHEMA.md §5 (reports):
  report_type, file_path, generated_by, generated_at, status
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ReportStatus(str, enum.Enum):
    """Current status of a report."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Report(Base):
    """Metadata record for a generated report."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    report_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Category/type of the report (e.g. 'revenue', 'department_analytics').",
    )
    format: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        default="csv",
        doc="Output format: 'csv', 'xlsx', or 'pdf'.",
    )
    file_path: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
        doc="Storage path to the generated file. NULL until generation completes.",
    )
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who requested the report. SET NULL if user is deleted.",
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="UTC timestamp when report generation completed.",
    )
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(
            ReportStatus, name="report_status", values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=ReportStatus.PENDING,
        server_default="pending",
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
    generator: Mapped[User | None] = relationship(
        "User",
        back_populates="reports",
        lazy="selectin",
        doc="The user who requested this report.",
    )

    def __repr__(self) -> str:
        return f"<Report id={self.id}" f" type={self.report_type!r}" f" status={self.status.value}>"
