"""
SearchRepository — PostgreSQL resolution of FAISS chunk IDs with Milestone 11 enterprise authorization.

Responsibilities:
  - Accept a list of chunk UUIDs returned by FAISS.
  - Resolve them to (DocumentChunk + Document) metadata in ONE batched query.
  - Filter using the centralized DocumentAccessService SQL filters (owner, shares, department, org-wide).
  - Automatically exclude soft-deleted, archived, expired, and deleted lifecycle documents.
  - Return results keyed by chunk_id for O(1) lookup in the service layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.document_access_service import DocumentAccessService, DocumentPermission

# ---------------------------------------------------------------------------
# Result dataclass — carries all fields the service / schema needs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkWithDocument:
    """Resolved chunk + document metadata returned from a batched DB query."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_owner_id: uuid.UUID
    document_name: str
    chunk_number: int
    content: str
    file_type: str | None
    created_at: datetime
    version_number: int = 1
    department_id: uuid.UUID | None = None
    confidentiality: str = "internal"
    lifecycle_status: str = "active"


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class SearchRepository:
    """Resolves FAISS chunk IDs to full chunk + document metadata with enterprise authorization."""

    def __init__(self, db: AsyncSession) -> None:
        self._session = db

    async def get_chunks_with_documents(
        self,
        chunk_ids: list[uuid.UUID],
        *,
        actor: User | None = None,
        owner_id: uuid.UUID | None = None,
        required_permission: DocumentPermission = DocumentPermission.VIEW,
        document_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, ChunkWithDocument]:
        """
        Fetch chunk + document metadata for a list of chunk UUIDs with enterprise authorization.

        Args:
            chunk_ids:           Chunk UUIDs returned by FAISS.
            actor:               Authenticated user to evaluate access grants/department against.
            owner_id:            (Legacy fallback) Restricts to specific owner_id if actor not provided.
            required_permission: Required permission level.
            document_id:         Optional restriction to a specific document (for document-scoped AI).

        Returns:
            Dict mapping chunk_id → ChunkWithDocument.
        """
        if not chunk_ids:
            return {}

        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.chunk_number,
                DocumentChunk.content,
                DocumentChunk.created_at,
                Document.file_name,
                Document.owner_id,
                Document.file_type,
                DocumentChunk.version_number,
                Document.department_id,
                Document.confidentiality,
                Document.lifecycle_status,
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.id.in_(chunk_ids))
        )

        if document_id is not None:
            stmt = stmt.where(Document.id == document_id)

        if actor is not None:
            auth_filters = DocumentAccessService.build_authorization_filter(
                actor,
                required_permission=required_permission,
                include_archived=False,
                include_deleted=False,
            )
            for cond in auth_filters:
                stmt = stmt.where(cond)
        elif owner_id is not None:
            # Legacy backwards compatibility path
            stmt = stmt.where(
                Document.owner_id == owner_id,
                Document.deleted_at.is_(None),
            )
        else:
            stmt = stmt.where(Document.deleted_at.is_(None))

        result = await self._session.execute(stmt)
        rows = result.fetchall()

        resolved: dict[uuid.UUID, ChunkWithDocument] = {}
        for row in rows:
            cid = row[0]
            conf_val = row[10].value if hasattr(row[10], "value") else str(row[10])
            life_val = row[11].value if hasattr(row[11], "value") else str(row[11])
            resolved[cid] = ChunkWithDocument(
                chunk_id=cid,
                document_id=row[1],
                chunk_number=row[2],
                content=row[3],
                created_at=row[4],
                document_name=row[5],
                document_owner_id=row[6],
                file_type=row[7],
                version_number=row[8] or 1,
                department_id=row[9],
                confidentiality=conf_val,
                lifecycle_status=life_val,
            )

        return resolved
