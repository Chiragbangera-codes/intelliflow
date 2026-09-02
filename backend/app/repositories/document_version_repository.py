"""
DocumentVersion repository — database access layer for document_versions table.

Handles atomic version creation, retrieval, version list ordering, and current
version pointer updates.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_version import DocumentVersion


class DocumentVersionRepository:
    """Handles all database operations for document_versions table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, version_id: uuid.UUID) -> DocumentVersion | None:
        """Fetch a specific version by its UUID."""
        result = await self._session.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_by_document_and_version(
        self,
        document_id: uuid.UUID,
        version_number: int,
    ) -> DocumentVersion | None:
        """Fetch a version by document_id and version_number."""
        result = await self._session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_current_version(self, document_id: uuid.UUID) -> DocumentVersion | None:
        """Fetch the active/current version for a document."""
        result = await self._session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_document(
        self,
        document_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentVersion]:
        """Fetch all versions for a document ordered newest-version first."""
        result = await self._session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_document(self, document_id: uuid.UUID) -> int:
        """Return total number of versions recorded for a document."""
        result = await self._session.execute(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
        )
        return result.scalar_one()

    async def get_next_version_number(self, document_id: uuid.UUID) -> int:
        """Determine the next sequential version number for a document."""
        result = await self._session.execute(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document_id
            )
        )
        max_ver = result.scalar_one_or_none()
        return (max_ver or 0) + 1

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        version_number: int,
        file_name: str,
        storage_path: str,
        created_by: uuid.UUID,
        file_type: str | None = None,
        file_size: int | None = None,
        checksum: str | None = None,
        is_current: bool = True,
        change_summary: str | None = None,
    ) -> DocumentVersion:
        """Insert a new document version."""
        if is_current:
            # Demote all existing versions to not current
            await self._session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .values(is_current=False)
            )

        version = DocumentVersion(
            document_id=document_id,
            version_number=version_number,
            file_name=file_name,
            storage_path=storage_path,
            created_by=created_by,
            file_type=file_type,
            file_size=file_size,
            checksum=checksum,
            is_current=is_current,
            change_summary=change_summary,
        )
        self._session.add(version)
        await self._session.flush()
        await self._session.refresh(version)
        return version

    async def set_current(self, version_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Mark a specific version as current, unsetting all other versions for the doc."""
        await self._session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .values(is_current=False)
        )
        await self._session.execute(
            update(DocumentVersion).where(DocumentVersion.id == version_id).values(is_current=True)
        )
        await self._session.flush()
