"""
DocumentShare repository — database access layer for document_shares table.

Handles access grant creation, retrieval, updates, revocation, and active share checks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_share import DocumentShare, DocumentSharePermission


class DocumentShareRepository:
    """Handles all database operations for document_shares table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, share_id: uuid.UUID) -> DocumentShare | None:
        """Fetch a specific share grant by its UUID."""
        result = await self._session.execute(
            select(DocumentShare).where(DocumentShare.id == share_id)
        )
        return result.scalar_one_or_none()

    async def get_active_share(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DocumentShare | None:
        """Fetch an active (non-revoked, non-expired) share for a specific user and document."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(DocumentShare).where(
                DocumentShare.document_id == document_id,
                DocumentShare.user_id == user_id,
                DocumentShare.revoked_at.is_(None),
                or_(
                    DocumentShare.expires_at.is_(None),
                    DocumentShare.expires_at > now,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_share_by_doc_and_user(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DocumentShare | None:
        """Fetch any share record (active or revoked) between a document and user."""
        result = await self._session.execute(
            select(DocumentShare).where(
                DocumentShare.document_id == document_id,
                DocumentShare.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_document(
        self,
        document_id: uuid.UUID,
        *,
        active_only: bool = True,
    ) -> list[DocumentShare]:
        """List all shares granted on a document."""
        query = select(DocumentShare).where(DocumentShare.document_id == document_id)
        if active_only:
            now = datetime.now(UTC)
            query = query.where(
                DocumentShare.revoked_at.is_(None),
                or_(
                    DocumentShare.expires_at.is_(None),
                    DocumentShare.expires_at > now,
                ),
            )
        query = query.order_by(DocumentShare.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentShare]:
        """List active shares granted TO a specific user."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(DocumentShare)
            .where(
                DocumentShare.user_id == user_id,
                DocumentShare.revoked_at.is_(None),
                or_(
                    DocumentShare.expires_at.is_(None),
                    DocumentShare.expires_at > now,
                ),
            )
            .order_by(DocumentShare.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create_or_update(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        granted_by: uuid.UUID,
        permission: DocumentSharePermission,
        expires_at: datetime | None = None,
    ) -> DocumentShare:
        """Create a new access grant or re-activate/update an existing one."""
        existing = await self.get_share_by_doc_and_user(document_id, user_id)
        if existing is not None:
            existing.permission = permission
            existing.granted_by = granted_by
            existing.expires_at = expires_at
            existing.revoked_at = None
            existing.created_at = datetime.now(UTC)
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        share = DocumentShare(
            document_id=document_id,
            user_id=user_id,
            granted_by=granted_by,
            permission=permission,
            expires_at=expires_at,
        )
        self._session.add(share)
        await self._session.flush()
        await self._session.refresh(share)
        return share

    async def update_share(
        self,
        share_id: uuid.UUID,
        *,
        permission: DocumentSharePermission | None = None,
        expires_at: datetime | None = None,
    ) -> DocumentShare | None:
        """Update permission or expiry on a share."""
        share = await self.get_by_id(share_id)
        if not share or share.revoked_at is not None:
            return None

        if permission is not None:
            share.permission = permission
        if expires_at is not None:
            share.expires_at = expires_at

        await self._session.flush()
        await self._session.refresh(share)
        return share

    async def revoke_share(self, share_id: uuid.UUID) -> bool:
        """Revoke a document access grant by setting revoked_at timestamp."""
        share = await self.get_by_id(share_id)
        if not share or share.revoked_at is not None:
            return False

        share.revoked_at = datetime.now(UTC)
        await self._session.flush()
        return True
