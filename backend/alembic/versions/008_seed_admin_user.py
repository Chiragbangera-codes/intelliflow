"""
Migration: 008_seed_admin_user — Seed default admin user

Revision ID: 008_seed_admin_user
Revises:     007_integrations_event_bus
Create Date: 2026-09-19

Seeds the default platform administrator account:
  - Email:    Admin@intelliflow.ai
  - Password: Admin@123456  (Argon2id hash — change after first login)
  - Role:     admin (00000000-0000-4000-8000-000000000001)
  - Status:   active

This migration is idempotent: uses INSERT ... ON CONFLICT DO NOTHING so
re-running it will not overwrite a password that has been changed in production.

DO NOT edit this migration after it has been applied to any environment.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "008_seed_admin_user"
down_revision: str | None = "007_integrations_event_bus"
branch_labels: str | None = None
depends_on: str | None = None

# ---------------------------------------------------------------------------
# Constants — must match 001_auth seed values
# ---------------------------------------------------------------------------
_ROLE_ADMIN = uuid.UUID("00000000-0000-4000-8000-000000000001")
_ADMIN_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000010")

# Pre-computed Argon2id hash for "Admin@123456"
# Generated with: PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
_ADMIN_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=2,p=2"
    "$94RI/TEQqOwikf234Yspzw"
    "$TDtwNn54TdgnfxOxUEEDaOONXm0BNWV6bLoB7FsDDtI"
)


def upgrade() -> None:
    """Seed the default admin user if it does not already exist."""
    now = datetime.now(timezone.utc)

    op.execute(
        sa.text("""
            INSERT INTO users (
                id, email, first_name, last_name, password_hash,
                role_id, status, created_at, updated_at
            ) VALUES (
                :id, :email, :first_name, :last_name, :password_hash,
                :role_id, :status, :created_at, :updated_at
            )
            ON CONFLICT (email) DO NOTHING
        """).bindparams(
            id=str(_ADMIN_USER_ID),
            email="admin@intelliflow.ai",
            first_name="System",
            last_name="Administrator",
            password_hash=_ADMIN_PASSWORD_HASH,
            role_id=str(_ROLE_ADMIN),
            status="active",
            created_at=now,
            updated_at=now,
        )
    )



def downgrade() -> None:
    """Remove the seeded admin user."""
    op.execute(
        sa.text("DELETE FROM users WHERE id = :uid").bindparams(
            uid=str(_ADMIN_USER_ID)
        )
    )
