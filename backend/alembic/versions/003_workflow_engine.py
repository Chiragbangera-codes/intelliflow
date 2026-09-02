"""
Migration: 003_workflow_engine — Phase 8 schema additions.

Revision ID: 003_workflow_engine
Revises:     002_database_schema
Create Date: 2026-08-28

Changes:
  1. Add 'waiting_approval' and 'rejected' to execution_status ENUM.
  2. Add performance indexes on:
       - workflows.is_active
       - workflow_executions.status

The 002 migration only indexed workflow_id and triggered_by on
workflow_executions; status-based queries (dashboard counts, admin
views) need an index on `status` for acceptable performance.

DO NOT edit this migration after it has been applied.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "003_workflow_engine"
down_revision: str | None = "002_database_schema"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply Phase 8 schema changes."""

    # ------------------------------------------------------------------
    # 1. Extend the execution_status PostgreSQL ENUM with new values.
    #
    # PostgreSQL's ALTER TYPE ... ADD VALUE requires a transaction commit
    # before the new value can be used. Alembic handles this correctly
    # when running synchronously; we use op.get_bind() to stay within the
    # migration's connection.
    #
    # The IF NOT EXISTS guard makes this idempotent — safe to re-apply.
    # ------------------------------------------------------------------
    bind = op.get_bind()

    # Add waiting_approval
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            "  ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'waiting_approval'; "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
    )

    # Add rejected
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            "  ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'rejected'; "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
    )

    # ------------------------------------------------------------------
    # 2. Add missing indexes
    # ------------------------------------------------------------------
    # Index for dashboard `is_active` filter and active-workflow listings.
    op.create_index(
        "ix_workflows_is_active",
        "workflows",
        ["is_active"],
        if_not_exists=True,
    )

    # Index for status-filtered queries on executions (pending/running counts).
    op.create_index(
        "ix_workflow_executions_status",
        "workflow_executions",
        ["status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """
    Reverse Phase 8 schema changes.

    Note: PostgreSQL does not support removing ENUM values without
    recreating the type. The ENUM removal is omitted here — the values
    simply become unused. The indexes are dropped safely.
    """
    op.drop_index("ix_workflow_executions_status", table_name="workflow_executions")
    op.drop_index("ix_workflows_is_active", table_name="workflows")
