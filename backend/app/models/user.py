"""
User ORM model.

Stores authentication and identity data for all system users.

Milestone 3 additions:
  - department_id  — nullable FK to departments (ON DELETE RESTRICT)
  - department     — many-to-one relationship (selectin)
  - employee_profile — one-to-one (selectin)
  - documents        — one-to-many (raise)
  - ai_conversations — one-to-many (raise)
  - notifications    — one-to-many (raise)
  - audit_logs       — one-to-many (raise)
  - reports          — one-to-many (raise)
  - workflows        — one-to-many created_by (raise)
  - workflow_executions — one-to-many triggered_by (raise)

Collections are lazy="raise" to prevent accidental loading of large
datasets. Load them explicitly via joined/selectin options in queries.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ai_conversation import AIConversation
    from app.models.audit_log import AuditLog
    from app.models.department import Department
    from app.models.document import Document
    from app.models.employee_profile import EmployeeProfile
    from app.models.notification import Notification
    from app.models.refresh_token import RefreshToken
    from app.models.report import Report
    from app.models.role import Role
    from app.models.workflow import Workflow
    from app.models.workflow_execution import WorkflowExecution


class UserStatus(str, enum.Enum):
    """
    Account authentication status.

    Only ACTIVE users may authenticate. INACTIVE and SUSPENDED users
    receive a 401 on login attempts.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(Base):
    """
    User account with authentication credentials and role assignment.

    Relationships:
      - role (many-to-one)       — loaded via selectin (async-safe)
      - department (many-to-one) — loaded via selectin
      - refresh_tokens (one-to-many) — cascade delete
      - employee_profile (one-to-one) — selectin
      - documents, ai_conversations, notifications, audit_logs,
        reports, workflows, workflow_executions — lazy="raise"
        (must be loaded explicitly to avoid accidental bulk loads)
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        doc="UUID primary key — non-sequential for security.",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        doc="Normalised (lowercase) email address — unique across all users.",
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Argon2id hash of the user's password. Never exposed in API responses.",
    )
    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Foreign key to roles. Deletion of a role that has users is blocked.",
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        doc=(
            "Optional FK to departments. "
            "RESTRICT prevents deleting a department that still has users."
        ),
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default="active",
    )
    last_login: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="UTC timestamp of the most recent successful login.",
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

    # --- Auth (Milestone 2) ---
    role: Mapped[Role] = relationship(
        "Role",
        lazy="selectin",
        doc="The role assigned to this user. Always loaded (selectin).",
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # --- Milestone 3 additions ---
    department: Mapped[Department | None] = relationship(
        "Department",
        back_populates="users",
        lazy="selectin",
        doc="The department this user belongs to.",
    )
    employee_profile: Mapped[EmployeeProfile | None] = relationship(
        "EmployeeProfile",
        foreign_keys="EmployeeProfile.user_id",
        back_populates="user",
        uselist=False,
        lazy="selectin",
        doc="HR profile record — one-to-one.",
    )

    # Collections: never eager-loaded. Use explicit options in queries.
    documents: Mapped[list[Document]] = relationship(
        "Document",
        back_populates="owner",
        foreign_keys="Document.owner_id",
        lazy="raise",
        doc="Documents owned by this user.",
    )
    ai_conversations: Mapped[list[AIConversation]] = relationship(
        "AIConversation",
        back_populates="user",
        lazy="raise",
        doc="AI conversation history for this user.",
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
        doc="Notifications targeted at this user.",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog",
        back_populates="user",
        foreign_keys="AuditLog.user_id",
        lazy="raise",
        doc="Audit log entries attributed to this user.",
    )
    reports: Mapped[list[Report]] = relationship(
        "Report",
        back_populates="generator",
        foreign_keys="Report.generated_by",
        lazy="raise",
        doc="Reports generated by this user.",
    )
    workflows: Mapped[list[Workflow]] = relationship(
        "Workflow",
        back_populates="creator",
        foreign_keys="Workflow.created_by",
        lazy="raise",
        doc="Workflow definitions created by this user.",
    )
    workflow_executions: Mapped[list[WorkflowExecution]] = relationship(
        "WorkflowExecution",
        back_populates="triggered_by_user",
        foreign_keys="WorkflowExecution.triggered_by",
        lazy="raise",
        doc="Workflow executions triggered by this user.",
    )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        """Return True if the user is active and not soft-deleted."""
        return self.status == UserStatus.ACTIVE and self.deleted_at is None

    @property
    def full_name(self) -> str:
        """Return the user's full display name."""
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} status={self.status.value}>"
