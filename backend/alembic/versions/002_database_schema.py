"""
Migration: 002_database_schema — Complete database schema (Milestone 3)

Revision ID: 002_database_schema
Revises:     001_auth
Create Date: 2026-08-16

Builds on the Milestone 2 authentication schema by adding all business
entity tables required for IntelliFlow AI.

Tables created (in FK dependency order):
  1.  departments
  2.  department_id column added to users
  3.  employee_profiles
  4.  documents
  5.  document_chunks
  6.  ai_embeddings
  7.  ai_conversations
  8.  workflows
  9.  workflow_steps
  10. workflow_executions
  11. notifications
  12. reports
  13. predictions
  14. audit_logs
  15. settings

PostgreSQL ENUM types created:
  - document_status    (pending, processing, processed, failed)
  - ocr_status         (pending, processing, completed, failed, skipped)
  - execution_status   (pending, running, completed, failed, cancelled)
  - notification_channel  (email, in_app, sms)
  - notification_priority (low, medium, high, critical)
  - report_status      (pending, generating, completed, failed)

Safety notes:
  - The 001_auth migration is NOT modified.
  - downgrade() drops tables in reverse FK dependency order.
  - ENUM types are created/dropped explicitly.
  - auth tables (roles, users, refresh_tokens) and their seed data
    are untouched.

DO NOT edit this migration after it has been applied to any environment.
Create a new migration (003_*) for any future schema changes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "002_database_schema"
down_revision: str | None = "001_auth"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply the migration — add all Milestone 3 tables."""

    # ------------------------------------------------------------------
    # 1. PostgreSQL ENUM types (must be created before the tables that use them)
    # ------------------------------------------------------------------
    document_status_enum = sa.Enum(
        "pending", "processing", "processed", "failed",
        name="document_status",
    )
    document_status_enum.create(op.get_bind(), checkfirst=True)

    ocr_status_enum = sa.Enum(
        "pending", "processing", "completed", "failed", "skipped",
        name="ocr_status",
    )
    ocr_status_enum.create(op.get_bind(), checkfirst=True)

    execution_status_enum = sa.Enum(
        "pending", "running", "completed", "failed", "cancelled",
        name="execution_status",
    )
    execution_status_enum.create(op.get_bind(), checkfirst=True)

    notification_channel_enum = sa.Enum(
        "email", "in_app", "sms",
        name="notification_channel",
    )
    notification_channel_enum.create(op.get_bind(), checkfirst=True)

    notification_priority_enum = sa.Enum(
        "low", "medium", "high", "critical",
        name="notification_priority",
    )
    notification_priority_enum.create(op.get_bind(), checkfirst=True)

    report_status_enum = sa.Enum(
        "pending", "generating", "completed", "failed",
        name="report_status",
    )
    report_status_enum.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 2. departments
    # ------------------------------------------------------------------
    op.create_table(
        "departments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
    )
    op.create_index("ix_departments_name", "departments", ["name"], unique=True)

    # ------------------------------------------------------------------
    # 3. Add department_id to users (nullable FK)
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("department_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_department_id",
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_users_department_id", "users", ["department_id"])

    # ------------------------------------------------------------------
    # 4. employee_profiles
    # ------------------------------------------------------------------
    op.create_table(
        "employee_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("employee_code", sa.String(50), nullable=True),
        sa.Column("date_of_joining", sa.Date(), nullable=True),
        sa.Column("designation", sa.String(200), nullable=True),
        sa.Column("salary", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("manager_id", sa.UUID(), nullable=True),
        sa.Column("emergency_contact", sa.String(500), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("profile_photo", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_employee_profiles"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_employee_profiles_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["users.id"],
            name="fk_employee_profiles_manager_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("user_id", name="uq_employee_profiles_user_id"),
    )
    op.create_index("ix_employee_profiles_user_id", "employee_profiles", ["user_id"])
    op.create_index(
        "ix_employee_profiles_employee_code",
        "employee_profiles",
        ["employee_code"],
        unique=True,
    )
    op.create_index("ix_employee_profiles_manager_id", "employee_profiles", ["manager_id"])

    # ------------------------------------------------------------------
    # 5. documents
    # ------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(2000), nullable=False),
        sa.Column("file_type", sa.String(100), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "processing", "processed", "failed",
                name="document_status",
                create_type=False,  # Type is created explicitly above; prevent double CREATE TYPE
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column(
            "ocr_status",
            postgresql.ENUM(
                "pending", "processing", "completed", "failed", "skipped",
                name="ocr_status",
                create_type=False,  # Type is created explicitly above; prevent double CREATE TYPE
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_documents_owner_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_file_name", "documents", ["file_name"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])

    # ------------------------------------------------------------------
    # 6. document_chunks
    # ------------------------------------------------------------------
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_chunks_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id",
            "chunk_number",
            name="uq_document_chunks_doc_chunk",
        ),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    # ------------------------------------------------------------------
    # 7. ai_embeddings
    # ------------------------------------------------------------------
    op.create_table(
        "ai_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_chunk_id", sa.UUID(), nullable=False),
        sa.Column("vector_reference", sa.String(500), nullable=True),
        sa.Column("embedding_model", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_embeddings"),
        sa.ForeignKeyConstraint(
            ["document_chunk_id"],
            ["document_chunks.id"],
            name="fk_ai_embeddings_document_chunk_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("document_chunk_id", name="uq_ai_embeddings_chunk_id"),
    )
    op.create_index(
        "ix_ai_embeddings_document_chunk_id",
        "ai_embeddings",
        ["document_chunk_id"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # 8. ai_conversations
    # ------------------------------------------------------------------
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("response_time", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_conversations"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_conversations_user_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_ai_conversations_user_id", "ai_conversations", ["user_id"])
    op.create_index("ix_ai_conversations_created_at", "ai_conversations", ["created_at"])

    # ------------------------------------------------------------------
    # 9. workflows
    # ------------------------------------------------------------------
    op.create_table(
        "workflows",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_workflows"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_workflows_created_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_workflows_created_by", "workflows", ["created_by"])

    # ------------------------------------------------------------------
    # 10. workflow_steps
    # ------------------------------------------------------------------
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=True),
        sa.Column("timeout", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_steps"),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name="fk_workflow_steps_workflow_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workflow_id",
            "step_number",
            name="uq_workflow_steps_wf_step",
        ),
    )
    op.create_index("ix_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"])

    # ------------------------------------------------------------------
    # 11. workflow_executions
    # ------------------------------------------------------------------
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("triggered_by", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "running", "completed", "failed", "cancelled",
                name="execution_status",
                create_type=False,  # Type is created explicitly above; prevent double CREATE TYPE
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("logs", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_executions"),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name="fk_workflow_executions_workflow_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.id"],
            name="fk_workflow_executions_triggered_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_workflow_executions_workflow_id", "workflow_executions", ["workflow_id"]
    )
    op.create_index(
        "ix_workflow_executions_triggered_by", "workflow_executions", ["triggered_by"]
    )

    # ------------------------------------------------------------------
    # 12. notifications
    # ------------------------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "channel",
            postgresql.ENUM(
                "email", "in_app", "sms",
                name="notification_channel",
                create_type=False,  # Type is created explicitly above; prevent double CREATE TYPE
            ),
            nullable=False,
            server_default="in_app",
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "priority",
            postgresql.ENUM(
                "low", "medium", "high", "critical",
                name="notification_priority",
                create_type=False,  # Type is created explicitly above; prevent double CREATE TYPE
            ),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_notifications_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    # ------------------------------------------------------------------
    # 13. reports
    # ------------------------------------------------------------------
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("report_type", sa.String(200), nullable=False),
        sa.Column("file_path", sa.String(2000), nullable=True),
        sa.Column("generated_by", sa.UUID(), nullable=True),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "generating", "completed", "failed",
                name="report_status",
                create_type=False,  # Type is created explicitly above; prevent double CREATE TYPE
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.ForeignKeyConstraint(
            ["generated_by"],
            ["users.id"],
            name="fk_reports_generated_by",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_reports_generated_by", "reports", ["generated_by"])

    # ------------------------------------------------------------------
    # 14. predictions
    # ------------------------------------------------------------------
    op.create_table(
        "predictions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=True),
        sa.Column("prediction", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("execution_time", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_predictions"),
    )

    # ------------------------------------------------------------------
    # 15. audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("table_name", sa.String(100), nullable=True),
        # record_id: plain UUID, NO foreign key — cross-table reference
        sa.Column("record_id", sa.UUID(), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_audit_logs_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ------------------------------------------------------------------
    # 16. settings
    # ------------------------------------------------------------------
    op.create_table(
        "settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_settings"),
        sa.UniqueConstraint("key", name="uq_settings_key"),
    )
    op.create_index("ix_settings_key", "settings", ["key"])


def downgrade() -> None:
    """Reverse the migration — drop all Milestone 3 additions."""

    # Drop tables in reverse FK dependency order
    op.drop_table("settings")
    op.drop_table("audit_logs")
    op.drop_table("predictions")
    op.drop_table("reports")
    op.drop_table("notifications")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_steps")
    op.drop_table("workflows")
    op.drop_table("ai_conversations")
    op.drop_table("ai_embeddings")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("employee_profiles")

    # Remove department_id from users before dropping departments
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    op.drop_column("users", "department_id")

    op.drop_table("departments")

    # Drop PostgreSQL ENUM types (reverse creation order)
    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notification_priority").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notification_channel").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="execution_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="ocr_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="document_status").drop(op.get_bind(), checkfirst=True)
