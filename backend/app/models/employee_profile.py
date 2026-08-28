"""
EmployeeProfile ORM model.

Stores HR-specific employee information that supplements the users table.
Authentication data (password hash, tokens, status) remains in users.

One-to-one relationship with users:
    users 1──1 employee_profiles

Self-referential manager relationship:
    manager_id → users.id (not employee_profiles.id, per DATABASE_SCHEMA.md)
    Loaded with lazy="select" to prevent recursive eager-loading chains.

Salary uses NUMERIC(12, 2) — never FLOAT for monetary values.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class EmployeeProfile(Base):
    """Additional HR data for an employee — one-to-one with users."""

    __tablename__ = "employee_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
        doc="One-to-one FK to the users table. Cannot delete a user who has a profile.",
    )
    employee_code: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        doc="Unique employee identifier (e.g. 'EMP-0042'). Null until assigned by HR.",
    )
    date_of_joining: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        doc="The employee's start date.",
    )
    designation: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        doc="Job title / designation (e.g. 'Senior Software Engineer').",
    )
    salary: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=True,
        doc="Gross salary. NUMERIC(12,2) — never FLOAT for monetary values.",
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc=(
            "FK to users.id — the employee's direct manager. "
            "SET NULL when the manager's user record is deleted."
        ),
    )
    emergency_contact: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Emergency contact name and phone number.",
    )
    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Residential or mailing address.",
    )
    profile_photo: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        doc="Storage path or URL for the profile photo. The image is never stored here.",
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
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="employee_profile",
        lazy="selectin",
        doc="The user this profile belongs to.",
    )

    # manager is loaded on-demand only to avoid recursive eager-loading chains.
    # E.g. loading EmployeeProfile → manager(User) → manager's EmployeeProfile
    # → manager's manager(User) → … would be unbounded with selectin.
    manager: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[manager_id],
        lazy="select",
        doc=(
            "The direct manager of this employee. "
            "Deliberately not eager-loaded to prevent recursive chain loading."
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<EmployeeProfile id={self.id}"
            f" user_id={self.user_id}"
            f" code={self.employee_code!r}>"
        )
