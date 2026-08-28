"""
Document repository — database access layer for document metadata.

Provides typed async methods for the documents table.
File content is never stored or retrieved here — only metadata.

Milestone 5 additions:
  - search by file_name (case-insensitive ILIKE)
  - status filter (DocumentStatus enum)
  - safe sorting allowlist (created_at, file_name, file_size)
  - matching count methods for accurate pagination
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus

# Safe sorting map preventing arbitrary SQL injection
_SORT_MAP: dict[str, Any] = {
    "created_at": Document.created_at.asc(),
    "-created_at": Document.created_at.desc(),
    "file_name": Document.file_name.asc(),
    "-file_name": Document.file_name.desc(),
    "file_size": Document.file_size.asc(),
    "-file_size": Document.file_size.desc(),
}


class DocumentRepository:
    """Handles all database operations for the documents table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        """
        Return an active document by its UUID.

        Args:
            document_id: The document's UUID primary key.

        Returns:
            The Document instance, or None if not found or soft-deleted.
        """
        result = await self._session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
        status: DocumentStatus | None = None,
        sort: str | None = None,
    ) -> list[Document]:
        """
        Return active documents belonging to a specific user with filtering/sorting.

        Args:
            owner_id: The owner user's UUID.
            limit:    Maximum records to return (default 20, max 100).
            offset:   Pagination offset.
            search:   Case-insensitive substring filter for file_name.
            status:   Filter by DocumentStatus enum.
            sort:     Sort expression from safe allowlist.

        Returns:
            List of active Document instances matching criteria.
        """
        effective_limit = min(max(limit, 1), 100)
        query = select(Document).where(
            Document.owner_id == owner_id,
            Document.deleted_at.is_(None),
        )

        if search and search.strip():
            query = query.where(Document.file_name.ilike(f"%{search.strip()}%"))

        if status is not None:
            query = query.where(Document.status == status)

        order_clause = _SORT_MAP.get(sort or "-created_at", Document.created_at.desc())
        query = query.order_by(order_clause).limit(effective_limit).offset(offset)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        file_name: str,
        storage_path: str,
        owner_id: uuid.UUID,
        file_type: str | None = None,
        file_size: int | None = None,
        checksum: str | None = None,
    ) -> Document:
        """
        Insert a new document metadata record.

        Args:
            file_name:    Original filename.
            storage_path: Path/key in object storage.
            owner_id:     UUID of the uploading user.
            file_type:    MIME type (e.g. 'application/pdf').
            file_size:    File size in bytes.
            checksum:     SHA-256 hex digest for integrity.

        Returns:
            The persisted Document instance with id populated.
        """
        document = Document(
            file_name=file_name,
            storage_path=storage_path,
            owner_id=owner_id,
            file_type=file_type,
            file_size=file_size,
            checksum=checksum,
            status=DocumentStatus.PENDING,
        )
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def soft_delete(self, document_id: uuid.UUID) -> None:
        """
        Soft-delete a document by setting deleted_at.

        Per DATABASE_SCHEMA.md §9, documents are never physically deleted.

        Args:
            document_id: The document's UUID.
        """
        await self._session.execute(
            update(Document).where(Document.id == document_id).values(deleted_at=datetime.now(UTC))
        )

    async def list_all_active(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
        status: DocumentStatus | None = None,
        sort: str | None = None,
    ) -> list[Document]:
        """
        Return all active (non-deleted) documents with search/filtering/sorting.

        Intended for admin/hr users who need a global view.
        Access control is enforced at the service layer.

        Args:
            limit:  Maximum records to return (default 20, max 100).
            offset: Pagination offset.
            search: Case-insensitive substring filter for file_name.
            status: Filter by DocumentStatus enum.
            sort:   Sort expression from safe allowlist.

        Returns:
            List of active Document instances matching criteria.
        """
        effective_limit = min(max(limit, 1), 100)
        query = select(Document).where(Document.deleted_at.is_(None))

        if search and search.strip():
            query = query.where(Document.file_name.ilike(f"%{search.strip()}%"))

        if status is not None:
            query = query.where(Document.status == status)

        order_clause = _SORT_MAP.get(sort or "-created_at", Document.created_at.desc())
        query = query.order_by(order_clause).limit(effective_limit).offset(offset)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        document_id: uuid.UUID,
        *,
        file_name: str | None = None,
        file_type: str | None = None,
        checksum: str | None = None,
    ) -> Document | None:
        """
        Partially update allowed document metadata fields.

        Only file_name, file_type, and checksum are updatable via API.
        status, ocr_status, storage_path, and owner_id are immutable
        at the API layer (enforced here by not accepting them).

        Args:
            document_id: UUID of the document to update.
            file_name:   New filename (optional).
            file_type:   New MIME type (optional).
            checksum:    New SHA-256 hex digest (optional).

        Returns:
            Refreshed Document instance, or None if not found.
        """
        values: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if file_name is not None:
            values["file_name"] = file_name
        if file_type is not None:
            values["file_type"] = file_type
        if checksum is not None:
            values["checksum"] = checksum

        await self._session.execute(
            update(Document)
            .where(Document.id == document_id, Document.deleted_at.is_(None))
            .values(**values)
        )
        return await self.get_by_id(document_id)

    async def count_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        search: str | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
        """
        Return the count of active documents owned by a user matching criteria.

        Args:
            owner_id: The owner user's UUID.
            search:   Optional search string.
            status:   Optional DocumentStatus filter.

        Returns:
            Integer count.
        """
        query = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.owner_id == owner_id,
                Document.deleted_at.is_(None),
            )
        )

        if search and search.strip():
            query = query.where(Document.file_name.ilike(f"%{search.strip()}%"))

        if status is not None:
            query = query.where(Document.status == status)

        result = await self._session.execute(query)
        return result.scalar_one()

    async def count_all_active(
        self,
        *,
        search: str | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
        """
        Return the total count of all active documents matching criteria.

        Args:
            search: Optional search string.
            status: Optional DocumentStatus filter.

        Returns:
            Integer count.
        """
        query = select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))

        if search and search.strip():
            query = query.where(Document.file_name.ilike(f"%{search.strip()}%"))

        if status is not None:
            query = query.where(Document.status == status)

        result = await self._session.execute(query)
        return result.scalar_one()
