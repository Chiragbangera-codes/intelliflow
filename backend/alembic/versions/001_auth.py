"""
Migration: 001_auth — Authentication tables

Revision ID: 001_auth
Revises:     (none — first migration)
Create Date: 2026-08-12

Creates the database structures required for Milestone 2 authentication:

  1. roles          — System role definitions (RBAC)
  2. user_status    — PostgreSQL ENUM type for account status
  3. users          — User accounts with auth credentials and role assignment
  4. refresh_tokens — Server-side refresh token records (stored as SHA-256 hashes)

Seeds the five default roles:
  - admin    : System administrator
  - manager  : Department manager
  - employee : Default role for self-registration
  - hr       : Human resources personnel
  - finance  : Finance department personnel

Safety notes:
  - This migration is deterministic and idempotent when run once.
  - downgrade() drops tables in reverse FK dependency order.
  - The user_status ENUM is created/dropped explicitly (PostgreSQL type ownership).
  - UUIDs are generated at migration time for seed data (consistent across deploys).

DO NOT edit this migration after it has been applied to any environment.
Create a new migration (002_*) for any schema changes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers — used by Alembic to build the migration chain
# ---------------------------------------------------------------------------
revision: str = "001_auth"
down_revision: str | None = None  # First migration in the chain
branch_labels: str | None = None
depends_on: str | None = None


# ---------------------------------------------------------------------------
# Pre-defined UUIDs for seed data (deterministic across environments)
# ---------------------------------------------------------------------------
_ROLE_ADMIN = uuid.UUID("00000000-0000-4000-8000-000000000001")
_ROLE_MANAGER = uuid.UUID("00000000-0000-4000-8000-000000000002")
_ROLE_EMPLOYEE = uuid.UUID("00000000-0000-4000-8000-000000000003")
_ROLE_HR = uuid.UUID("00000000-0000-4000-8000-000000000004")
_ROLE_FINANCE = uuid.UUID("00000000-0000-4000-8000-000000000005")


def upgrade() -> None:
    """Apply the migration — create auth tables and seed roles."""

    # ------------------------------------------------------------------
    # 1. roles table
    # ------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    # ------------------------------------------------------------------
    # 2. user_status ENUM type (PostgreSQL native enum)
    # ------------------------------------------------------------------
    user_status_enum = sa.Enum(
        "active", "inactive", "suspended",
        name="user_status",
    )
    user_status_enum.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 3. users table
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "inactive", "suspended",
                name="user_status",
                create_type=False,  # Type is created explicitly above; prevent double CREATE TYPE
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_login", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_users_role_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role_id", "users", ["role_id"])

    # ------------------------------------------------------------------
    # 4. refresh_tokens table
    # ------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # 5. Seed default roles
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("created_at", sa.TIMESTAMP(timezone=True)),
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "id": _ROLE_ADMIN,
                "name": "admin",
                "description": "System administrator with full platform access.",
                "created_at": now,
            },
            {
                "id": _ROLE_MANAGER,
                "name": "manager",
                "description": "Department manager with elevated permissions.",
                "created_at": now,
            },
            {
                "id": _ROLE_EMPLOYEE,
                "name": "employee",
                "description": "Standard employee — default role for self-registration.",
                "created_at": now,
            },
            {
                "id": _ROLE_HR,
                "name": "hr",
                "description": "Human resources personnel.",
                "created_at": now,
            },
            {
                "id": _ROLE_FINANCE,
                "name": "finance",
                "description": "Finance department personnel.",
                "created_at": now,
            },
        ],
    )


def downgrade() -> None:
    """Reverse the migration — drop auth tables in FK-safe order."""
    # Drop tables (FK dependency order: refresh_tokens → users → roles)
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("roles")

    # Drop the PostgreSQL ENUM type
    sa.Enum(name="user_status").drop(op.get_bind(), checkfirst=True)
