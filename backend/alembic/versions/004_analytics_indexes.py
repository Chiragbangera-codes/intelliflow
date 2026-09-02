"""
Migration: 004_analytics_indexes — Phase 9 schema additions.

Revision ID: 004_analytics_indexes
Revises:     003_workflow_engine
Create Date: 2026-08-31

Changes:
  1. Add `format` column (VARCHAR 10, nullable) to `reports` table.
     Stores the requested output format: 'csv', 'xlsx', or 'pdf'.
  2. Add performance indexes on:
       - predictions.model
       - predictions.created_at
       - reports.generated_by
       - reports.status

DO NOT edit this migration after it has been applied.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "004_analytics_indexes"
down_revision: str | None = "003_workflow_engine"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply Phase 9 schema changes."""

    # ------------------------------------------------------------------
    # 1. Add `format` column to reports table
    # ------------------------------------------------------------------
    op.add_column(
        "reports",
        sa.Column(
            "format",
            sa.String(10),
            nullable=True,
            server_default="csv",
        ),
    )

    # ------------------------------------------------------------------
    # 2. Add performance indexes
    # ------------------------------------------------------------------
    op.create_index(
        "ix_predictions_model",
        "predictions",
        ["model"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_predictions_created_at",
        "predictions",
        ["created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_reports_generated_by",
        "reports",
        ["generated_by"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_reports_status",
        "reports",
        ["status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Reverse Phase 9 schema changes."""
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_generated_by", table_name="reports")
    op.drop_index("ix_predictions_created_at", table_name="predictions")
    op.drop_index("ix_predictions_model", table_name="predictions")
    op.drop_column("reports", "format")
