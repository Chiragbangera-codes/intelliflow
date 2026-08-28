"""
Document service — business logic for document management and storage.

Enforces server-side authorization, streaming storage integration,
SHA-256 integrity verification, search/filter/sort capabilities,
and audit logging.

Authorization rules (server-enforced):
  - admin / hr : full list (all documents), get any, upload, download any, update any, delete any
  - employee   : list own documents only, get own, upload, download own, update own, delete own
  - manager    : same as employee for this milestone

Security rules enforced here:
  - owner_id is ALWAYS set to the authenticated user's id.
  - status / ocr_status are server-controlled — initialised to PENDING.
  - PATCH accepts only: file_name, file_type, checksum.
  - Direct file storage cleanup on database transaction failure.
"""

import math
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.document import DocumentStatus
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
    PaginatedDocumentResponse,
)
from app.services.storage_service import StorageService

logger = get_logger(__name__)

# Roles with global document visibility and administrative access
_ADMIN_ROLES = frozenset({"admin", "hr"})


class DocumentService:
    """Encapsulates all document metadata and file storage business logic."""

    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService | None = None,
    ) -> None:
        """Inject the database session, audit repository, and storage manager."""
        self._session = session
        self._documents = DocumentRepository(session)
        self._audit = AuditLogRepository(session)
        self._storage = storage_service or StorageService()

    # ------------------------------------------------------------------
    # Upload (Milestone 5)
    # ------------------------------------------------------------------

    async def upload_document(
        self,
        file: UploadFile,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """
        Stream an uploaded file to storage and record its metadata.

        Security:
          - owner_id is strictly derived from actor.id.
          - Streamed chunk-by-chunk with SHA-256 computed on the fly.
          - 100 MB max size enforced during streaming.
          - Orphan files are cleaned up if database persistence fails.

        Args:
            file:       The FastAPI UploadFile multipart object.
            actor:      The authenticated user.
            ip_address: Client IP for audit logging.

        Returns:
            DocumentResponse with persisted metadata.
        """
        # 1. Stream file to disk storage
        stored = await self._storage.save_upload_file(file, owner_id=actor.id)

        # 2. Persist Document record in PostgreSQL
        try:
            doc = await self._documents.create(
                file_name=stored.file_name,
                storage_path=stored.storage_path,
                owner_id=actor.id,
                file_type=stored.file_type,
                file_size=stored.file_size,
                checksum=stored.checksum,
            )

            # 3. Create audit trail
            await self._audit.create(
                action="document.upload",
                user_id=actor.id,
                table_name="documents",
                record_id=doc.id,
                new_value={
                    "file_name": doc.file_name,
                    "file_size": doc.file_size,
                    "checksum": doc.checksum,
                    "file_type": doc.file_type,
                    "owner_id": str(doc.owner_id),
                },
                ip_address=ip_address,
            )

            await self._session.commit()
            await self._session.refresh(doc)
            logger.info("Document uploaded & persisted: id=%s owner=%s", doc.id, actor.id)
            return DocumentResponse.model_validate(doc)

        except Exception as exc:
            # Transaction failed — clean up the stored file to avoid orphans
            logger.exception(
                "Database persistence failed for uploaded file: %s", stored.storage_path
            )
            self._storage.delete_file(stored.storage_path)
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record document metadata.",
            ) from exc

    # ------------------------------------------------------------------
    # Download (Milestone 5)
    # ------------------------------------------------------------------

    async def get_document_file_path(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
    ) -> tuple[Path, str, str, int]:
        """
        Verify permissions and return the physical file path for download.

        Access:
          - admin / hr : any document
          - others     : only own documents

        Returns:
            Tuple of (resolved_path, original_filename, content_type, file_size).

        Raises:
            HTTPException 404: If document or physical file not found.
            HTTPException 403: If user is not authorized.
        """
        doc = await self._documents.get_by_id(document_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )

        if actor.role.name not in _ADMIN_ROLES and doc.owner_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this document.",
            )

        resolved_path = self._storage.resolve_path(doc.storage_path)
        content_type = doc.file_type or "application/octet-stream"
        file_size = doc.file_size or resolved_path.stat().st_size

        return resolved_path, doc.file_name, content_type, file_size

    # ------------------------------------------------------------------
    # Read — list (extended with search, status filter, sorting)
    # ------------------------------------------------------------------

    async def list_documents(
        self,
        *,
        actor: User,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status_filter: DocumentStatus | None = None,
        sort: str | None = None,
    ) -> PaginatedDocumentResponse:
        """
        Return a paginated, filtered, and sorted list of documents.

        Access:
          - admin / hr : all active documents
          - others     : only documents owned by the authenticated user
        """
        effective_size = min(max(page_size, 1), 100)
        offset = (max(page, 1) - 1) * effective_size

        if actor.role.name in _ADMIN_ROLES:
            documents = await self._documents.list_all_active(
                limit=effective_size,
                offset=offset,
                search=search,
                status=status_filter,
                sort=sort,
            )
            total = await self._documents.count_all_active(
                search=search,
                status=status_filter,
            )
        else:
            documents = await self._documents.get_by_owner(
                actor.id,
                limit=effective_size,
                offset=offset,
                search=search,
                status=status_filter,
                sort=sort,
            )
            total = await self._documents.count_by_owner(
                actor.id,
                search=search,
                status=status_filter,
            )

        total_pages = max(math.ceil(total / effective_size), 1) if total else 1

        return PaginatedDocumentResponse(
            data=[DocumentResponse.model_validate(d) for d in documents],
            meta={
                "page": page,
                "page_size": effective_size,
                "total_items": total,
                "total_pages": total_pages,
            },
        )

    # ------------------------------------------------------------------
    # Read — single
    # ------------------------------------------------------------------

    async def get_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
    ) -> DocumentResponse:
        """
        Return metadata for a single document by UUID.

        Access:
          - admin / hr : any document
          - others     : only own documents

        Raises:
            HTTPException 404: Not found or soft-deleted.
            HTTPException 403: Not the owner.
        """
        doc = await self._documents.get_by_id(document_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )

        if actor.role.name not in _ADMIN_ROLES and doc.owner_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this document.",
            )

        return DocumentResponse.model_validate(doc)

    # ------------------------------------------------------------------
    # Create (metadata only — backwards compatibility)
    # ------------------------------------------------------------------

    async def create_document(
        self,
        data: DocumentCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """
        Create a document metadata record.

        Security:
          - owner_id is ALWAYS set to actor.id.
          - status and ocr_status are initialized to PENDING.
        """
        doc = await self._documents.create(
            file_name=data.file_name,
            storage_path=data.storage_path,
            owner_id=actor.id,
            file_type=data.file_type,
            file_size=data.file_size,
            checksum=data.checksum,
        )

        await self._audit.create(
            action="document.create",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            new_value={
                "file_name": doc.file_name,
                "file_type": doc.file_type,
                "owner_id": str(doc.owner_id),
            },
            ip_address=ip_address,
        )

        await self._session.commit()
        await self._session.refresh(doc)

        logger.info("Document created: id=%s owner=%s", doc.id, actor.id)
        return DocumentResponse.model_validate(doc)

    # ------------------------------------------------------------------
    # Update metadata
    # ------------------------------------------------------------------

    async def update_document(
        self,
        document_id: uuid.UUID,
        data: DocumentUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """
        Partially update allowed metadata fields (file_name, file_type, checksum).

        status, ocr_status, storage_path, and owner_id are immutable.
        """
        doc = await self._documents.get_by_id(document_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )

        if actor.role.name not in _ADMIN_ROLES and doc.owner_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this document.",
            )

        old_value = {
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "checksum": doc.checksum,
        }

        updated = await self._documents.update(
            document_id,
            file_name=data.file_name,
            file_type=data.file_type,
            checksum=data.checksum,
        )

        await self._audit.create(
            action="document.update",
            user_id=actor.id,
            table_name="documents",
            record_id=document_id,
            old_value=old_value,
            new_value={
                "file_name": data.file_name,
                "file_type": data.file_type,
                "checksum": data.checksum,
            },
            ip_address=ip_address,
        )

        await self._session.commit()

        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )

        await self._session.refresh(updated)
        logger.info("Document updated: id=%s actor=%s", document_id, actor.id)
        return DocumentResponse.model_validate(updated)

    # ------------------------------------------------------------------
    # Delete (soft-delete)
    # ------------------------------------------------------------------

    async def delete_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """
        Soft-delete a document record.

        Per DATABASE_SCHEMA.md §9, records are soft-deleted with audit trail.
        """
        doc = await self._documents.get_by_id(document_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )

        if actor.role.name not in _ADMIN_ROLES and doc.owner_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this document.",
            )

        await self._documents.soft_delete(document_id)

        await self._audit.create(
            action="document.delete",
            user_id=actor.id,
            table_name="documents",
            record_id=document_id,
            old_value={"file_name": doc.file_name, "owner_id": str(doc.owner_id)},
            ip_address=ip_address,
        )

        await self._session.commit()
        logger.info("Document soft-deleted: id=%s actor=%s", document_id, actor.id)
