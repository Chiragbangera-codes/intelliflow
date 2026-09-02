"""
Document repository — database access layer for document metadata (Milestone 11).

Provides typed async methods for the documents table with advanced enterprise filtering,
version awareness, access grant filtering, bulk queries, and lifecycle management.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import (
    Document,
    DocumentConfidentiality,
    DocumentLifecycleStatus,
    DocumentStatus,
)
from app.models.document_share import DocumentShare
from app.models.user import User
from app.services.document_access_service import DocumentAccessService, DocumentPermission

# Safe sorting map preventing SQL injection
_SORT_MAP: dict[str, Any] = {
    "created_at": Document.created_at.asc(),
    "-created_at": Document.created_at.desc(),
    "updated_at": Document.updated_at.asc(),
    "-updated_at": Document.updated_at.desc(),
    "file_name": Document.file_name.asc(),
    "-file_name": Document.file_name.desc(),
    "title": Document.title.asc(),
    "-title": Document.title.desc(),
    "file_size": Document.file_size.asc(),
    "-file_size": Document.file_size.desc(),
}


class DocumentRepository:
    """Handles all database operations for the documents table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self,
        document_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> Document | None:
        """Return a document by UUID."""
        query = (
            select(Document)
            .options(
                selectinload(Document.shares),
                selectinload(Document.versions),
                selectinload(Document.owner),
                selectinload(Document.department),
            )
            .where(Document.id == document_id)
        )
        if not include_deleted:
            query = query.where(Document.deleted_at.is_(None))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_ids(
        self,
        document_ids: list[uuid.UUID],
        *,
        include_deleted: bool = False,
    ) -> list[Document]:
        """Fetch multiple documents by UUIDs in a single query."""
        if not document_ids:
            return []
        query = (
            select(Document)
            .options(
                selectinload(Document.shares),
                selectinload(Document.versions),
                selectinload(Document.owner),
                selectinload(Document.department),
            )
            .where(Document.id.in_(document_ids))
        )
        if not include_deleted:
            query = query.where(Document.deleted_at.is_(None))
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_authorized_documents(
        self,
        actor: User,
        *,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
        status: DocumentStatus | None = None,
        lifecycle_status: DocumentLifecycleStatus | None = None,
        department_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        category: str | None = None,
        document_type: str | None = None,
        confidentiality: DocumentConfidentiality | None = None,
        tag: str | None = None,
        shared_with_me: bool = False,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort: str | None = None,
        include_archived: bool = True,
        include_deleted: bool = False,
    ) -> list[Document]:
        """
        Return paginated, authorized documents for the actor matching search/filter criteria.
        """
        effective_limit = min(max(limit, 1), 100)
        query = select(Document).options(
            selectinload(Document.shares),
            selectinload(Document.versions),
            selectinload(Document.owner),
            selectinload(Document.department),
        )

        # Apply enterprise authorization rules
        auth_filters = DocumentAccessService.build_authorization_filter(
            actor,
            required_permission=DocumentPermission.VIEW,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )
        for cond in auth_filters:
            query = query.where(cond)

        # Filters
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Document.file_name.ilike(term),
                    Document.title.ilike(term),
                    Document.description.ilike(term),
                )
            )

        if status is not None:
            query = query.where(Document.status == status)

        if lifecycle_status is not None:
            query = query.where(Document.lifecycle_status == lifecycle_status)

        if department_id is not None:
            query = query.where(Document.department_id == department_id)

        if owner_id is not None:
            query = query.where(Document.owner_id == owner_id)

        if category and category.strip():
            query = query.where(Document.category.ilike(f"%{category.strip()}%"))

        if document_type and document_type.strip():
            query = query.where(Document.document_type.ilike(f"%{document_type.strip()}%"))

        if confidentiality is not None:
            query = query.where(Document.confidentiality == confidentiality)

        if shared_with_me:
            now = datetime.now(UTC)
            share_subquery = select(DocumentShare.document_id).where(
                DocumentShare.user_id == actor.id,
                DocumentShare.revoked_at.is_(None),
                or_(
                    DocumentShare.expires_at.is_(None),
                    DocumentShare.expires_at > now,
                ),
            )
            query = query.where(Document.id.in_(share_subquery))

        if date_from is not None:
            query = query.where(Document.created_at >= date_from)

        if date_to is not None:
            query = query.where(Document.created_at <= date_to)

        order_clause = _SORT_MAP.get(sort or "-created_at", Document.created_at.desc())
        query = query.order_by(order_clause).limit(effective_limit).offset(offset)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_authorized_documents(
        self,
        actor: User,
        *,
        search: str | None = None,
        status: DocumentStatus | None = None,
        lifecycle_status: DocumentLifecycleStatus | None = None,
        department_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        category: str | None = None,
        document_type: str | None = None,
        confidentiality: DocumentConfidentiality | None = None,
        tag: str | None = None,
        shared_with_me: bool = False,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_archived: bool = True,
        include_deleted: bool = False,
    ) -> int:
        """Count total authorized documents matching criteria."""
        query = select(func.count()).select_from(Document)

        auth_filters = DocumentAccessService.build_authorization_filter(
            actor,
            required_permission=DocumentPermission.VIEW,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )
        for cond in auth_filters:
            query = query.where(cond)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Document.file_name.ilike(term),
                    Document.title.ilike(term),
                    Document.description.ilike(term),
                )
            )

        if status is not None:
            query = query.where(Document.status == status)

        if lifecycle_status is not None:
            query = query.where(Document.lifecycle_status == lifecycle_status)

        if department_id is not None:
            query = query.where(Document.department_id == department_id)

        if owner_id is not None:
            query = query.where(Document.owner_id == owner_id)

        if category and category.strip():
            query = query.where(Document.category.ilike(f"%{category.strip()}%"))

        if document_type and document_type.strip():
            query = query.where(Document.document_type.ilike(f"%{document_type.strip()}%"))

        if confidentiality is not None:
            query = query.where(Document.confidentiality == confidentiality)

        if shared_with_me:
            now = datetime.now(UTC)
            share_subquery = select(DocumentShare.document_id).where(
                DocumentShare.user_id == actor.id,
                DocumentShare.revoked_at.is_(None),
                or_(
                    DocumentShare.expires_at.is_(None),
                    DocumentShare.expires_at > now,
                ),
            )
            query = query.where(Document.id.in_(share_subquery))

        if date_from is not None:
            query = query.where(Document.created_at >= date_from)

        if date_to is not None:
            query = query.where(Document.created_at <= date_to)

        result = await self._session.execute(query)
        return result.scalar_one()

    async def create(
        self,
        *,
        file_name: str,
        storage_path: str,
        owner_id: uuid.UUID,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        document_type: str | None = None,
        tags: list[str] | None = None,
        department_id: uuid.UUID | None = None,
        confidentiality: DocumentConfidentiality = DocumentConfidentiality.INTERNAL,
        retention_period_days: int | None = None,
        expires_at: datetime | None = None,
        file_type: str | None = None,
        file_size: int | None = None,
        checksum: str | None = None,
    ) -> Document:
        """Insert a new document metadata record."""
        document = Document(
            file_name=file_name,
            title=title or file_name,
            description=description,
            category=category,
            document_type=document_type,
            tags=tags or [],
            storage_path=storage_path,
            owner_id=owner_id,
            department_id=department_id,
            confidentiality=confidentiality,
            retention_period_days=retention_period_days,
            expires_at=expires_at,
            file_type=file_type,
            file_size=file_size,
            checksum=checksum,
            status=DocumentStatus.PENDING,
            lifecycle_status=DocumentLifecycleStatus.ACTIVE,
            activated_at=datetime.now(UTC),
        )
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def update_metadata(
        self,
        document_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        document_type: str | None = None,
        tags: list[str] | None = None,
        department_id: uuid.UUID | None = None,
        confidentiality: DocumentConfidentiality | None = None,
        retention_period_days: int | None = None,
        expires_at: datetime | None = None,
        file_name: str | None = None,
        file_type: str | None = None,
        checksum: str | None = None,
        storage_path: str | None = None,
        file_size: int | None = None,
    ) -> Document | None:
        """Update metadata fields for a document."""
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}

        if title is not None:
            values["title"] = title
        if description is not None:
            values["description"] = description
        if category is not None:
            values["category"] = category
        if document_type is not None:
            values["document_type"] = document_type
        if tags is not None:
            values["tags"] = tags
        if department_id is not None:
            values["department_id"] = department_id
        if confidentiality is not None:
            values["confidentiality"] = confidentiality
        if retention_period_days is not None:
            values["retention_period_days"] = retention_period_days
        if expires_at is not None:
            values["expires_at"] = expires_at
        if file_name is not None:
            values["file_name"] = file_name
        if file_type is not None:
            values["file_type"] = file_type
        if checksum is not None:
            values["checksum"] = checksum
        if storage_path is not None:
            values["storage_path"] = storage_path
        if file_size is not None:
            values["file_size"] = file_size

        await self._session.execute(
            update(Document)
            .where(Document.id == document_id, Document.deleted_at.is_(None))
            .values(**values)
        )
        await self._session.flush()
        return await self.get_by_id(document_id)

    async def update_lifecycle_status(
        self,
        document_id: uuid.UUID,
        new_status: DocumentLifecycleStatus,
    ) -> Document | None:
        """Transition document lifecycle status and stamp timestamps."""
        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "lifecycle_status": new_status,
            "updated_at": now,
        }

        if new_status == DocumentLifecycleStatus.ACTIVE:
            values["activated_at"] = now
            values["deleted_at"] = None
        elif new_status == DocumentLifecycleStatus.ARCHIVED:
            values["archived_at"] = now
        elif new_status == DocumentLifecycleStatus.DELETED:
            values["deleted_at"] = now

        await self._session.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )
        await self._session.flush()
        return await self.get_by_id(document_id, include_deleted=True)

    async def soft_delete(self, document_id: uuid.UUID) -> None:
        """Soft-delete a document."""
        now = datetime.now(UTC)
        await self._session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                deleted_at=now,
                lifecycle_status=DocumentLifecycleStatus.DELETED,
                updated_at=now,
            )
        )
        await self._session.flush()

    async def get_expired_active_documents(self, limit: int = 500) -> list[Document]:
        """Find active documents whose expires_at timestamp has passed."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(Document)
            .where(
                Document.deleted_at.is_(None),
                Document.lifecycle_status == DocumentLifecycleStatus.ACTIVE,
                Document.expires_at.is_not(None),
                Document.expires_at <= now,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    # =========================================================================
    # Legacy backwards compatibility methods
    # =========================================================================

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

    async def list_all_active(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
        status: DocumentStatus | None = None,
        sort: str | None = None,
    ) -> list[Document]:
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

    async def count_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        search: str | None = None,
        status: DocumentStatus | None = None,
    ) -> int:
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
        query = select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
        if search and search.strip():
            query = query.where(Document.file_name.ilike(f"%{search.strip()}%"))
        if status is not None:
            query = query.where(Document.status == status)
        result = await self._session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        document_id: uuid.UUID,
        *,
        file_name: str | None = None,
        file_type: str | None = None,
        checksum: str | None = None,
    ) -> Document | None:
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if file_name is not None:
            values["file_name"] = file_name
            values["title"] = file_name
        if file_type is not None:
            values["file_type"] = file_type
        if checksum is not None:
            values["checksum"] = checksum

        await self._session.execute(
            update(Document)
            .where(Document.id == document_id, Document.deleted_at.is_(None))
            .values(**values)
        )
        await self._session.flush()
        return await self.get_by_id(document_id)
