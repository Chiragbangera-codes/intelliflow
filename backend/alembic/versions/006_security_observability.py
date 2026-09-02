"""
Migration: 006_security_observability — Milestone 12 performance and security indexes.

Revision ID: 006_security_observability
Revises:     005_document_intelligence
Create Date: 2026-08-31

Changes:
  1. Create indexes on `audit_logs` for security event filtering & 24h metrics:
     - `idx_audit_logs_action`
     - `idx_audit_logs_user_id`
     - `idx_audit_logs_created_at`
  2. Create indexes on `refresh_tokens` for session management & rapid token revocation:
     - `idx_refresh_tokens_user_id_revoked_at`
     - `idx_refresh_tokens_expires_at`
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_security_observability"
down_revision: str | None = "005_document_intelligence"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. audit_logs indexes
    op.create_index(
        "idx_audit_logs_action",
        "audit_logs",
        ["action"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_audit_logs_user_id",
        "audit_logs",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_audit_logs_created_at",
        "audit_logs",
        [sa.text("created_at DESC")],
        unique=False,
        if_not_exists=True,
    )

    # 2. refresh_tokens indexes
    op.create_index(
        "idx_refresh_tokens_user_id_revoked_at",
        "refresh_tokens",
        ["user_id", "revoked_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "idx_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_refresh_tokens_expires_at", table_name="refresh_tokens", if_exists=True)
    op.drop_index("idx_refresh_tokens_user_id_revoked_at", table_name="refresh_tokens", if_exists=True)
    op.drop_index("idx_audit_logs_created_at", table_name="audit_logs", if_exists=True)
    op.drop_index("idx_audit_logs_user_id", table_name="audit_logs", if_exists=True)
    op.drop_index("idx_audit_logs_action", table_name="audit_logs", if_exists=True)
