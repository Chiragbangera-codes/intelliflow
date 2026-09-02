"""
Migration: 005_document_intelligence — Milestone 11 schema additions.

Revision ID: 005_document_intelligence
Revises:     004_analytics_indexes
Create Date: 2026-08-31

Changes:
  1. Create ENUMs:
     - `document_lifecycle_status` ('draft', 'active', 'archived', 'expired', 'deleted')
     - `document_confidentiality` ('public', 'internal', 'confidential', 'restricted')
     - `document_share_permission` ('view', 'download', 'edit', 'manage')
  2. Alter `documents` table:
     - Add `title` (VARCHAR 500, nullable)
     - Add `description` (TEXT, nullable)
     - Add `category` (VARCHAR 100, nullable)
     - Add `document_type` (VARCHAR 100, nullable)
     - Add `tags` (JSONB, nullable, default '[]')
     - Add `department_id` (UUID, nullable, FK to departments.id ON DELETE SET NULL)
     - Add `confidentiality` (document_confidentiality, nullable=False, default 'internal')
     - Add `lifecycle_status` (document_lifecycle_status, nullable=False, default 'active')
     - Add `retention_period_days` (INTEGER, nullable)
     - Add `activated_at` (TIMESTAMP WITH TIME ZONE, nullable)
     - Add `archived_at` (TIMESTAMP WITH TIME ZONE, nullable)
     - Add `expires_at` (TIMESTAMP WITH TIME ZONE, nullable)
  3. Create `document_versions` table:
     - id (UUID PK)
     - document_id (UUID FK to documents.id ON DELETE CASCADE)
     - version_number (INTEGER NOT NULL)
     - file_name (VARCHAR 500 NOT NULL)
     - storage_path (VARCHAR 2000 NOT NULL)
     - file_type (VARCHAR 100 NULL)
     - file_size (BIGINT NULL)
     - checksum (VARCHAR 64 NULL)
     - created_by (UUID FK to users.id ON DELETE RESTRICT)
     - is_current (BOOLEAN NOT NULL DEFAULT true)
     - change_summary (TEXT NULL)
     - created_at (TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now())
     - UniqueConstraint(document_id, version_number)
  4. Create `document_shares` table:
     - id (UUID PK)
     - document_id (UUID FK to documents.id ON DELETE CASCADE)
     - user_id (UUID FK to users.id ON DELETE CASCADE)
     - granted_by (UUID FK to users.id ON DELETE RESTRICT)
     - permission (document_share_permission NOT NULL DEFAULT 'view')
     - expires_at (TIMESTAMP WITH TIME ZONE NULL)
     - created_at (TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now())
     - revoked_at (TIMESTAMP WITH TIME ZONE NULL)
     - UniqueConstraint(document_id, user_id)
  5. Alter `document_chunks` table:
     - Add `version_id` (UUID NULL, FK to document_versions.id ON DELETE CASCADE)
     - Add `version_number` (INTEGER NOT NULL DEFAULT 1)
  6. Backfill existing documents:
     - Populate version 1 in document_versions for all existing documents.
  7. Add performance indexes on:
     - documents: department_id, lifecycle_status, confidentiality, expires_at, title, category, document_type
     - document_versions: document_id, created_by, is_current, (document_id, is_current)
     - document_shares: document_id, user_id, (user_id, document_id), (document_id, revoked_at)
     - document_chunks: version_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "005_document_intelligence"
down_revision: str | None = "004_analytics_indexes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply Milestone 11 document intelligence schema additions."""

    # ------------------------------------------------------------------
    # 1. Create Enums
    # ------------------------------------------------------------------
    postgresql.ENUM(
        "draft", "active", "archived", "expired", "deleted",
        name="document_lifecycle_status",
    ).create(op.get_bind(), checkfirst=True)

    lifecycle_enum = postgresql.ENUM(
        "draft", "active", "archived", "expired", "deleted",
        name="document_lifecycle_status",
        create_type=False,
    )

    postgresql.ENUM(
        "public", "internal", "confidential", "restricted",
        name="document_confidentiality",
    ).create(op.get_bind(), checkfirst=True)

    confidentiality_enum = postgresql.ENUM(
        "public", "internal", "confidential", "restricted",
        name="document_confidentiality",
        create_type=False,
    )

    postgresql.ENUM(
        "view", "download", "edit", "manage",
        name="document_share_permission",
    ).create(op.get_bind(), checkfirst=True)

    share_perm_enum = postgresql.ENUM(
        "view", "download", "edit", "manage",
        name="document_share_permission",
        create_type=False,
    )

    # ------------------------------------------------------------------
    # 2. Alter documents table
    # ------------------------------------------------------------------
    op.add_column("documents", sa.Column("title", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("category", sa.String(100), nullable=True))
    op.add_column("documents", sa.Column("document_type", sa.String(100), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "department_id",
            sa.UUID(),
            sa.ForeignKey("departments.id", ondelete="SET NULL", name="fk_documents_department_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "confidentiality",
            confidentiality_enum,
            nullable=False,
            server_default="internal",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "lifecycle_status",
            lifecycle_enum,
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column("documents", sa.Column("retention_period_days", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True))

    # ------------------------------------------------------------------
    # 3. Create document_versions table
    # ------------------------------------------------------------------
    op.create_table(
        "document_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(2000), nullable=False),
        sa.Column("file_type", sa.String(100), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_versions_document_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_document_versions_created_by",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_doc_ver",
        ),
    )

    # ------------------------------------------------------------------
    # 4. Create document_shares table
    # ------------------------------------------------------------------
    op.create_table(
        "document_shares",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("granted_by", sa.UUID(), nullable=False),
        sa.Column(
            "permission",
            share_perm_enum,
            nullable=False,
            server_default="view",
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_document_shares"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_shares_document_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_document_shares_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            name="fk_document_shares_granted_by",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "document_id",
            "user_id",
            name="uq_document_shares_doc_user",
        ),
    )

    # ------------------------------------------------------------------
    # 5. Alter document_chunks table
    # ------------------------------------------------------------------
    op.add_column(
        "document_chunks",
        sa.Column(
            "version_id",
            sa.UUID(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE", name="fk_document_chunks_version_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    # ------------------------------------------------------------------
    # 6. Backfill version 1 for existing documents
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO document_versions (
            id, document_id, version_number, file_name, storage_path,
            file_type, file_size, checksum, created_by, is_current,
            change_summary, created_at
        )
        SELECT
            gen_random_uuid(), id, 1, file_name, storage_path,
            file_type, file_size, checksum, owner_id, true,
            'Initial version', created_at
        FROM documents
        ON CONFLICT DO NOTHING;
        """
    )

    # ------------------------------------------------------------------
    # 7. Create Indexes
    # ------------------------------------------------------------------
    op.create_index("ix_documents_department_id", "documents", ["department_id"], if_not_exists=True)
    op.create_index("ix_documents_lifecycle_status", "documents", ["lifecycle_status"], if_not_exists=True)
    op.create_index("ix_documents_confidentiality", "documents", ["confidentiality"], if_not_exists=True)
    op.create_index("ix_documents_expires_at", "documents", ["expires_at"], if_not_exists=True)
    op.create_index("ix_documents_title", "documents", ["title"], if_not_exists=True)
    op.create_index("ix_documents_category", "documents", ["category"], if_not_exists=True)
    op.create_index("ix_documents_document_type", "documents", ["document_type"], if_not_exists=True)

    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"], if_not_exists=True)
    op.create_index("ix_document_versions_created_by", "document_versions", ["created_by"], if_not_exists=True)
    op.create_index("ix_document_versions_is_current", "document_versions", ["is_current"], if_not_exists=True)
    op.create_index(
        "ix_document_versions_doc_current",
        "document_versions",
        ["document_id", "is_current"],
        if_not_exists=True,
    )

    op.create_index("ix_document_shares_document_id", "document_shares", ["document_id"], if_not_exists=True)
    op.create_index("ix_document_shares_user_id", "document_shares", ["user_id"], if_not_exists=True)
    op.create_index(
        "ix_document_shares_user_doc",
        "document_shares",
        ["user_id", "document_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_document_shares_doc_revoked",
        "document_shares",
        ["document_id", "revoked_at"],
        if_not_exists=True,
    )
    op.create_index("ix_document_shares_expires_at", "document_shares", ["expires_at"], if_not_exists=True)

    op.create_index("ix_document_chunks_version_id", "document_chunks", ["version_id"], if_not_exists=True)


def downgrade() -> None:
    """Reverse Milestone 11 document intelligence schema additions."""
    op.drop_index("ix_document_chunks_version_id", table_name="document_chunks")

    op.drop_index("ix_document_shares_expires_at", table_name="document_shares")
    op.drop_index("ix_document_shares_doc_revoked", table_name="document_shares")
    op.drop_index("ix_document_shares_user_doc", table_name="document_shares")
    op.drop_index("ix_document_shares_user_id", table_name="document_shares")
    op.drop_index("ix_document_shares_document_id", table_name="document_shares")

    op.drop_index("ix_document_versions_doc_current", table_name="document_versions")
    op.drop_index("ix_document_versions_is_current", table_name="document_versions")
    op.drop_index("ix_document_versions_created_by", table_name="document_versions")
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")

    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_category", table_name="documents")
    op.drop_index("ix_documents_title", table_name="documents")
    op.drop_index("ix_documents_expires_at", table_name="documents")
    op.drop_index("ix_documents_confidentiality", table_name="documents")
    op.drop_index("ix_documents_lifecycle_status", table_name="documents")
    op.drop_index("ix_documents_department_id", table_name="documents")

    op.drop_column("document_chunks", "version_number")
    op.drop_column("document_chunks", "version_id")

    op.drop_table("document_shares")
    op.drop_table("document_versions")

    op.drop_column("documents", "expires_at")
    op.drop_column("documents", "archived_at")
    op.drop_column("documents", "activated_at")
    op.drop_column("documents", "retention_period_days")
    op.drop_column("documents", "lifecycle_status")
    op.drop_column("documents", "confidentiality")
    op.drop_column("documents", "department_id")
    op.drop_column("documents", "tags")
    op.drop_column("documents", "document_type")
    op.drop_column("documents", "category")
    op.drop_column("documents", "description")
    op.drop_column("documents", "title")

    op.execute("DROP TYPE IF EXISTS document_share_permission;")
    op.execute("DROP TYPE IF EXISTS document_confidentiality;")
    op.execute("DROP TYPE IF EXISTS document_lifecycle_status;")
