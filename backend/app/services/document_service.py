"""
DocumentService — Comprehensive enterprise document management business logic (Milestone 11).

Orchestrates:
  - Document upload & initial version 1 creation
  - Document versioning: create new version, list versions, restore version, version downloads
  - Access grants & sharing: share document, list shares, update share, revoke share
  - Enterprise lifecycle: draft, active, archived, expired, deleted transitions with audit
  - Advanced filtering & search (full-text, metadata, tags, department, category, confidentiality, shared)
  - Bulk operations: archive, restore, delete, tag, share with per-item RBAC enforcement
  - Document activity timeline with sanitized audit events
  - Notifications integration via NotificationService
  - Secure streaming downloads and in-browser previews
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.document import (
    Document,
    DocumentConfidentiality,
    DocumentLifecycleStatus,
    DocumentStatus,
)
from app.models.document_share import DocumentShare, DocumentSharePermission
from app.models.notification import NotificationChannel, NotificationPriority
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.department_repository import DepartmentRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_share_repository import DocumentShareRepository
from app.repositories.document_version_repository import DocumentVersionRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.document import (
    BulkOperationResponse,
    BulkOperationResultItem,
    DocumentActivityItem,
    DocumentActivityResponse,
    DocumentCreate,
    DocumentResponse,
    DocumentShareCreate,
    DocumentShareResponse,
    DocumentShareUpdate,
    DocumentUpdate,
    DocumentVersionResponse,
    PaginatedDocumentResponse,
)
from app.services.document_access_service import DocumentAccessService
from app.services.notification_service import NotificationService
from app.services.storage_service import StorageService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_OCR_TASK_NAME = "tasks.process_document_ocr"


def _format_document_response(
    doc: Document,
    actor: User,
    active_share: DocumentShare | None = None,
) -> DocumentResponse:
    """Helper to serialize Document to DocumentResponse with permission metadata."""
    perm = DocumentAccessService.evaluate_permission(doc, actor, active_share)
    perm_str = perm.value if perm is not None else None

    # Calculate version metadata
    versions = getattr(doc, "versions", [])
    version_count = len(versions) if versions else 1
    current_ver = 1
    if versions:
        for v in versions:
            if v.is_current:
                current_ver = v.version_number
                break

    return DocumentResponse(
        id=doc.id,
        file_name=doc.file_name,
        title=doc.title,
        description=doc.description,
        category=doc.category,
        document_type=doc.document_type,
        tags=doc.tags or [],
        storage_path=doc.storage_path,
        file_type=doc.file_type,
        file_size=doc.file_size,
        owner_id=doc.owner_id,
        department_id=doc.department_id,
        confidentiality=doc.confidentiality,
        lifecycle_status=doc.lifecycle_status,
        status=doc.status,
        ocr_status=doc.ocr_status,
        checksum=doc.checksum,
        retention_period_days=doc.retention_period_days,
        activated_at=doc.activated_at,
        archived_at=doc.archived_at,
        expires_at=doc.expires_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        version_count=version_count,
        current_version_number=current_ver,
        user_permission=perm_str,
    )


class DocumentService:
    """Encapsulates all enterprise document management business logic."""

    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService | None = None,
    ) -> None:
        self._session = session
        self._documents = DocumentRepository(session)
        self._versions = DocumentVersionRepository(session)
        self._shares = DocumentShareRepository(session)
        self._users = UserRepository(session)
        self._departments = DepartmentRepository(session)
        self._audit = AuditLogRepository(session)
        self._notif = NotificationService(session)
        self._notifs = NotificationRepository(session)
        self._access = DocumentAccessService(session)
        self._storage = storage_service or StorageService()

    # =========================================================================
    # 1. Document Upload & Initial Version
    # =========================================================================

    async def upload_document(
        self,
        file: UploadFile,
        *,
        actor: User,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        document_type: str | None = None,
        tags: list[str] | None = None,
        department_id: uuid.UUID | None = None,
        confidentiality: DocumentConfidentiality = DocumentConfidentiality.INTERNAL,
        retention_period_days: int | None = None,
        expires_at: datetime | None = None,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """Stream an uploaded file to storage, create Document record and Version 1."""
        stored = await self._storage.save_upload_file(file, owner_id=actor.id)

        try:
            dept_id = department_id or actor.department_id

            doc = await self._documents.create(
                file_name=stored.file_name,
                title=title or stored.file_name,
                description=description,
                category=category,
                document_type=document_type,
                tags=tags or [],
                department_id=dept_id,
                confidentiality=confidentiality,
                retention_period_days=retention_period_days,
                expires_at=expires_at,
                storage_path=stored.storage_path,
                owner_id=actor.id,
                file_type=stored.file_type,
                file_size=stored.file_size,
                checksum=stored.checksum,
            )

            await self._versions.create(
                document_id=doc.id,
                version_number=1,
                file_name=stored.file_name,
                storage_path=stored.storage_path,
                created_by=actor.id,
                file_type=stored.file_type,
                file_size=stored.file_size,
                checksum=stored.checksum,
                is_current=True,
                change_summary="Initial upload (Version 1)",
            )

            await self._audit.create(
                action="document.upload",
                user_id=actor.id,
                table_name="documents",
                record_id=doc.id,
                new_value={
                    "file_name": doc.file_name,
                    "file_size": doc.file_size,
                    "checksum": doc.checksum,
                    "version": 1,
                    "owner_id": str(doc.owner_id),
                },
                ip_address=ip_address,
            )

            await self._session.commit()
            await self._session.refresh(doc)

            try:
                celery_app.send_task(_OCR_TASK_NAME, args=[str(doc.id)])
            except Exception as task_exc:
                logger.warning("Failed to auto-dispatch OCR task for doc %s: %s", doc.id, task_exc)

            return _format_document_response(doc, actor)

        except Exception as exc:
            logger.exception("Failed to persist document metadata: %s", exc)
            self._storage.delete_file(stored.storage_path)
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record document metadata.",
            ) from exc

    # =========================================================================
    # 2. Document Versioning
    # =========================================================================

    async def create_new_version(
        self,
        document_id: uuid.UUID,
        file: UploadFile,
        *,
        actor: User,
        change_summary: str | None = None,
        ip_address: str | None = None,
    ) -> DocumentVersionResponse:
        """Upload a new version of an existing document."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_edit(doc, actor, active_share):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to upload new versions of this document.",
            )

        stored = await self._storage.save_upload_file(file, owner_id=doc.owner_id)

        try:
            next_ver_num = await self._versions.get_next_version_number(doc.id)

            version = await self._versions.create(
                document_id=doc.id,
                version_number=next_ver_num,
                file_name=stored.file_name,
                storage_path=stored.storage_path,
                created_by=actor.id,
                file_type=stored.file_type,
                file_size=stored.file_size,
                checksum=stored.checksum,
                is_current=True,
                change_summary=change_summary or f"Version {next_ver_num}",
            )

            await self._documents.update_metadata(
                doc.id,
                file_name=stored.file_name,
                storage_path=stored.storage_path,
                file_type=stored.file_type,
                file_size=stored.file_size,
                checksum=stored.checksum,
            )

            await self._audit.create(
                action="document.version_created",
                user_id=actor.id,
                table_name="document_versions",
                record_id=version.id,
                new_value={
                    "document_id": str(doc.id),
                    "version_number": next_ver_num,
                    "file_name": version.file_name,
                    "checksum": version.checksum,
                },
                ip_address=ip_address,
            )

            if doc.owner_id != actor.id:
                try:
                    await self._notifs.create(
                        user_id=doc.owner_id,
                        title="New Document Version Uploaded",
                        message=f"{actor.first_name} {actor.last_name} uploaded Version {next_ver_num} of '{doc.display_name}'.",
                        channel=NotificationChannel.IN_APP,
                        priority=NotificationPriority.MEDIUM,
                    )
                except Exception as notif_exc:
                    logger.warning("Failed to send version notification: %s", notif_exc)

            await self._session.commit()

            try:
                celery_app.send_task(_OCR_TASK_NAME, args=[str(doc.id)])
            except Exception as task_exc:
                logger.warning("Failed to auto-dispatch OCR task: %s", task_exc)

            return DocumentVersionResponse.model_validate(version)

        except Exception as exc:
            logger.exception("Failed to create new document version: %s", exc)
            self._storage.delete_file(stored.storage_path)
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record document version.",
            ) from exc

    async def list_versions(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
    ) -> list[DocumentVersionResponse]:
        """List all versions of a document ordered newest-version first."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_view(doc, actor, active_share):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this document's versions.",
            )

        versions = await self._versions.list_by_document(document_id)
        return [DocumentVersionResponse.model_validate(v) for v in versions]

    async def get_version(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        actor: User,
    ) -> DocumentVersionResponse:
        """Get a single version metadata."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_view(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        version = await self._versions.get_by_id(version_id)
        if not version or version.document_id != document_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

        return DocumentVersionResponse.model_validate(version)

    async def restore_version(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentVersionResponse:
        """Restore an old version by creating a NEW version that copies the old version's file."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_edit(doc, actor, active_share):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to restore versions for this document.",
            )

        target_ver = await self._versions.get_by_id(version_id)
        if not target_ver or target_ver.document_id != document_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

        next_ver_num = await self._versions.get_next_version_number(doc.id)

        new_version = await self._versions.create(
            document_id=doc.id,
            version_number=next_ver_num,
            file_name=target_ver.file_name,
            storage_path=target_ver.storage_path,
            created_by=actor.id,
            file_type=target_ver.file_type,
            file_size=target_ver.file_size,
            checksum=target_ver.checksum,
            is_current=True,
            change_summary=f"Restored from Version {target_ver.version_number}",
        )

        await self._documents.update_metadata(
            doc.id,
            file_name=target_ver.file_name,
            storage_path=target_ver.storage_path,
            file_type=target_ver.file_type,
            file_size=target_ver.file_size,
            checksum=target_ver.checksum,
        )

        await self._audit.create(
            action="document.version_restored",
            user_id=actor.id,
            table_name="document_versions",
            record_id=new_version.id,
            new_value={
                "document_id": str(doc.id),
                "restored_from_version": target_ver.version_number,
                "new_version_number": next_ver_num,
            },
            ip_address=ip_address,
        )

        await self._session.commit()

        try:
            celery_app.send_task(_OCR_TASK_NAME, args=[str(doc.id)])
        except Exception as task_exc:
            logger.warning("Failed to auto-dispatch OCR task: %s", task_exc)

        return DocumentVersionResponse.model_validate(new_version)

    async def get_version_file_path(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        actor: User,
    ) -> tuple[Path, str, str, int]:
        """Verify download authorization and return the version's physical file path."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_download(doc, actor, active_share):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to download this document.",
            )

        ver = await self._versions.get_by_id(version_id)
        if not ver or ver.document_id != document_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

        resolved_path = self._storage.resolve_path(ver.storage_path)
        content_type = ver.file_type or "application/octet-stream"
        file_size = ver.file_size or resolved_path.stat().st_size

        return resolved_path, ver.file_name, content_type, file_size

    # =========================================================================
    # 3. Document Sharing & Access Grants
    # =========================================================================

    async def share_document(
        self,
        document_id: uuid.UUID,
        payload: DocumentShareCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentShareResponse:
        """Create or update an access grant for a specific user."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to share this document.",
            )

        target_user = await self._users.get_by_id(payload.user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found."
            )

        if target_user.id == doc.owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create a share grant for the document owner.",
            )

        share = await self._shares.create_or_update(
            document_id=doc.id,
            user_id=target_user.id,
            granted_by=actor.id,
            permission=payload.permission,
            expires_at=payload.expires_at,
        )

        await self._audit.create(
            action="document.shared",
            user_id=actor.id,
            table_name="document_shares",
            record_id=share.id,
            new_value={
                "document_id": str(doc.id),
                "grantee_id": str(target_user.id),
                "permission": payload.permission.value,
                "expires_at": str(payload.expires_at) if payload.expires_at else None,
            },
            ip_address=ip_address,
        )

        try:
            await self._notifs.create(
                user_id=target_user.id,
                title="Document Shared With You",
                message=f"{actor.first_name} {actor.last_name} shared '{doc.display_name}' with you ({payload.permission.value} access).",
                channel=NotificationChannel.IN_APP,
                priority=NotificationPriority.MEDIUM,
            )
        except Exception as notif_exc:
            logger.warning("Failed to send share notification: %s", notif_exc)

        await self._session.commit()

        return DocumentShareResponse(
            id=share.id,
            document_id=share.document_id,
            user_id=share.user_id,
            user_email=target_user.email,
            user_name=f"{target_user.first_name} {target_user.last_name}",
            granted_by=share.granted_by,
            grantor_name=f"{actor.first_name} {actor.last_name}",
            permission=share.permission,
            expires_at=share.expires_at,
            created_at=share.created_at,
            revoked_at=share.revoked_at,
            is_active=share.is_active,
        )

    async def list_shares(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
    ) -> list[DocumentShareResponse]:
        """List active access grants on a document."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            if not active_share:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
            return [
                DocumentShareResponse(
                    id=active_share.id,
                    document_id=active_share.document_id,
                    user_id=active_share.user_id,
                    user_email=actor.email,
                    user_name=f"{actor.first_name} {actor.last_name}",
                    granted_by=active_share.granted_by,
                    permission=active_share.permission,
                    expires_at=active_share.expires_at,
                    created_at=active_share.created_at,
                    revoked_at=active_share.revoked_at,
                    is_active=active_share.is_active,
                )
            ]

        shares = await self._shares.list_by_document(document_id, active_only=True)
        results: list[DocumentShareResponse] = []
        for s in shares:
            u = s.user
            g = s.grantor
            results.append(
                DocumentShareResponse(
                    id=s.id,
                    document_id=s.document_id,
                    user_id=s.user_id,
                    user_email=u.email if u else None,
                    user_name=f"{u.first_name} {u.last_name}" if u else None,
                    granted_by=s.granted_by,
                    grantor_name=f"{g.first_name} {g.last_name}" if g else None,
                    permission=s.permission,
                    expires_at=s.expires_at,
                    created_at=s.created_at,
                    revoked_at=s.revoked_at,
                    is_active=s.is_active,
                )
            )
        return results

    async def update_share(
        self,
        document_id: uuid.UUID,
        share_id: uuid.UUID,
        payload: DocumentShareUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentShareResponse:
        """Update an existing share's permissions or expiration."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        share = await self._shares.get_by_id(share_id)
        if not share or share.document_id != document_id or share.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Share grant not found."
            )

        updated = await self._shares.update_share(
            share_id,
            permission=payload.permission,
            expires_at=payload.expires_at,
        )

        await self._audit.create(
            action="document.share_updated",
            user_id=actor.id,
            table_name="document_shares",
            record_id=share_id,
            new_value={
                "permission": payload.permission.value if payload.permission else None,
                "expires_at": str(payload.expires_at) if payload.expires_at else None,
            },
            ip_address=ip_address,
        )
        await self._session.commit()

        u = updated.user if updated else None
        return DocumentShareResponse(
            id=updated.id,
            document_id=updated.document_id,
            user_id=updated.user_id,
            user_email=u.email if u else None,
            user_name=f"{u.first_name} {u.last_name}" if u else None,
            granted_by=updated.granted_by,
            permission=updated.permission,
            expires_at=updated.expires_at,
            created_at=updated.created_at,
            revoked_at=updated.revoked_at,
            is_active=updated.is_active,
        )

    async def revoke_share(
        self,
        document_id: uuid.UUID,
        share_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """Revoke a document access grant."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        share = await self._shares.get_by_id(share_id)
        if not share or share.document_id != document_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Share grant not found."
            )

        grantee_id = share.user_id
        await self._shares.revoke_share(share_id)

        await self._audit.create(
            action="document.share_revoked",
            user_id=actor.id,
            table_name="document_shares",
            record_id=share_id,
            new_value={"document_id": str(doc.id), "grantee_id": str(grantee_id)},
            ip_address=ip_address,
        )

        try:
            await self._notifs.create(
                user_id=grantee_id,
                title="Document Access Revoked",
                message=f"Your access to '{doc.display_name}' has been revoked by {actor.first_name} {actor.last_name}.",
                channel=NotificationChannel.IN_APP,
                priority=NotificationPriority.LOW,
            )
        except Exception as notif_exc:
            logger.warning("Failed to send revocation notification: %s", notif_exc)

        await self._session.commit()

    # =========================================================================
    # 4. Document Lifecycle Management
    # =========================================================================

    async def activate_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """Activate a draft or restored document."""
        doc = await self._documents.get_by_id(document_id, include_deleted=True)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        updated = await self._documents.update_lifecycle_status(
            doc.id, DocumentLifecycleStatus.ACTIVE
        )
        await self._audit.create(
            action="document.activated",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            ip_address=ip_address,
        )
        await self._session.commit()
        return _format_document_response(updated or doc, actor, active_share)

    async def archive_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """Archive an active document."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        if doc.lifecycle_status == DocumentLifecycleStatus.ARCHIVED:
            return _format_document_response(doc, actor, active_share)

        updated = await self._documents.update_lifecycle_status(
            doc.id, DocumentLifecycleStatus.ARCHIVED
        )
        await self._audit.create(
            action="document.archived",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            ip_address=ip_address,
        )
        await self._session.commit()
        return _format_document_response(updated or doc, actor, active_share)

    async def restore_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """Restore an archived, expired, or deleted document to active state."""
        doc = await self._documents.get_by_id(document_id, include_deleted=True)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        updated = await self._documents.update_lifecycle_status(
            doc.id, DocumentLifecycleStatus.ACTIVE
        )
        await self._audit.create(
            action="document.restored",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            ip_address=ip_address,
        )
        await self._session.commit()
        return _format_document_response(updated or doc, actor, active_share)

    async def expire_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """Manually mark a document as expired."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        updated = await self._documents.update_lifecycle_status(
            doc.id, DocumentLifecycleStatus.EXPIRED
        )
        await self._audit.create(
            action="document.expired",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            ip_address=ip_address,
        )
        await self._session.commit()
        return _format_document_response(updated or doc, actor, active_share)

    async def delete_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """Soft-delete a document."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_manage(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

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

    # =========================================================================
    # 5. Document List & Detail with Advanced Filters
    # =========================================================================

    async def list_documents(
        self,
        *,
        actor: User,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status_filter: DocumentStatus | None = None,
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
    ) -> PaginatedDocumentResponse:
        """Return paginated, authorized documents matching multi-dimensional filters."""
        effective_size = min(max(page_size, 1), 100)
        offset = (max(page, 1) - 1) * effective_size

        docs = await self._documents.list_authorized_documents(
            actor,
            limit=effective_size,
            offset=offset,
            search=search,
            status=status_filter,
            lifecycle_status=lifecycle_status,
            department_id=department_id,
            owner_id=owner_id,
            category=category,
            document_type=document_type,
            confidentiality=confidentiality,
            tag=tag,
            shared_with_me=shared_with_me,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            include_archived=True,
            include_deleted=False,
        )

        total = await self._documents.count_authorized_documents(
            actor,
            search=search,
            status=status_filter,
            lifecycle_status=lifecycle_status,
            department_id=department_id,
            owner_id=owner_id,
            category=category,
            document_type=document_type,
            confidentiality=confidentiality,
            tag=tag,
            shared_with_me=shared_with_me,
            date_from=date_from,
            date_to=date_to,
            include_archived=True,
            include_deleted=False,
        )

        total_pages = max(math.ceil(total / effective_size), 1) if total else 1

        return PaginatedDocumentResponse(
            data=[_format_document_response(d, actor) for d in docs],
            meta={
                "page": page,
                "page_size": effective_size,
                "total_items": total,
                "total_pages": total_pages,
            },
        )

    async def get_document(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
    ) -> DocumentResponse:
        """Return full document metadata."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_view(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        return _format_document_response(doc, actor, active_share)

    async def update_document(
        self,
        document_id: uuid.UUID,
        data: DocumentUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """Update allowed document metadata fields."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_edit(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        updated = await self._documents.update_metadata(
            document_id,
            title=data.title,
            description=data.description,
            category=data.category,
            document_type=data.document_type,
            tags=data.tags,
            department_id=data.department_id,
            confidentiality=data.confidentiality,
            retention_period_days=data.retention_period_days,
            expires_at=data.expires_at,
            file_name=data.file_name,
            file_type=data.file_type,
            checksum=data.checksum,
        )

        await self._audit.create(
            action="document.update",
            user_id=actor.id,
            table_name="documents",
            record_id=document_id,
            new_value=data.model_dump(exclude_unset=True, mode="json"),
            ip_address=ip_address,
        )
        await self._session.commit()

        return _format_document_response(updated or doc, actor, active_share)

    # =========================================================================
    # 6. Bulk Operations
    # =========================================================================

    async def bulk_archive(
        self,
        document_ids: list[uuid.UUID],
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> BulkOperationResponse:
        """Archive a batch of documents, checking individual authorization."""
        if len(document_ids) > settings.DOCUMENT_BULK_MAX_ITEMS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Batch size exceeds maximum limit of {settings.DOCUMENT_BULK_MAX_ITEMS} items.",
            )

        docs = await self._documents.get_by_ids(document_ids)
        doc_map = {d.id: d for d in docs}

        results: list[BulkOperationResultItem] = []
        succeeded = 0
        failed = 0

        for doc_id in document_ids:
            doc = doc_map.get(doc_id)
            if not doc:
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Document not found."
                    )
                )
                failed += 1
                continue

            active_share = await self._shares.get_active_share(doc.id, actor.id)
            if not DocumentAccessService.can_manage(doc, actor, active_share):
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Insufficient permissions."
                    )
                )
                failed += 1
                continue

            await self._documents.update_lifecycle_status(doc.id, DocumentLifecycleStatus.ARCHIVED)
            succeeded += 1
            results.append(BulkOperationResultItem(document_id=doc_id, success=True))

        await self._audit.create(
            action="document.bulk_archive",
            user_id=actor.id,
            table_name="documents",
            new_value={"total": len(document_ids), "succeeded": succeeded, "failed": failed},
            ip_address=ip_address,
        )
        await self._session.commit()

        return BulkOperationResponse(
            message=f"Bulk archive completed: {succeeded} succeeded, {failed} failed.",
            total=len(document_ids),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def bulk_restore(
        self,
        document_ids: list[uuid.UUID],
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> BulkOperationResponse:
        """Restore a batch of archived/expired/deleted documents."""
        if len(document_ids) > settings.DOCUMENT_BULK_MAX_ITEMS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Batch size exceeds maximum limit of {settings.DOCUMENT_BULK_MAX_ITEMS} items.",
            )

        docs = await self._documents.get_by_ids(document_ids, include_deleted=True)
        doc_map = {d.id: d for d in docs}

        results: list[BulkOperationResultItem] = []
        succeeded = 0
        failed = 0

        for doc_id in document_ids:
            doc = doc_map.get(doc_id)
            if not doc:
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Document not found."
                    )
                )
                failed += 1
                continue

            active_share = await self._shares.get_active_share(doc.id, actor.id)
            if not DocumentAccessService.can_manage(doc, actor, active_share):
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Insufficient permissions."
                    )
                )
                failed += 1
                continue

            await self._documents.update_lifecycle_status(doc.id, DocumentLifecycleStatus.ACTIVE)
            succeeded += 1
            results.append(BulkOperationResultItem(document_id=doc_id, success=True))

        await self._audit.create(
            action="document.bulk_restore",
            user_id=actor.id,
            table_name="documents",
            new_value={"total": len(document_ids), "succeeded": succeeded, "failed": failed},
            ip_address=ip_address,
        )
        await self._session.commit()

        return BulkOperationResponse(
            message=f"Bulk restore completed: {succeeded} succeeded, {failed} failed.",
            total=len(document_ids),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def bulk_delete(
        self,
        document_ids: list[uuid.UUID],
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> BulkOperationResponse:
        """Soft-delete a batch of documents."""
        if len(document_ids) > settings.DOCUMENT_BULK_MAX_ITEMS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Batch size exceeds maximum limit of {settings.DOCUMENT_BULK_MAX_ITEMS} items.",
            )

        docs = await self._documents.get_by_ids(document_ids)
        doc_map = {d.id: d for d in docs}

        results: list[BulkOperationResultItem] = []
        succeeded = 0
        failed = 0

        for doc_id in document_ids:
            doc = doc_map.get(doc_id)
            if not doc:
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Document not found."
                    )
                )
                failed += 1
                continue

            active_share = await self._shares.get_active_share(doc.id, actor.id)
            if not DocumentAccessService.can_manage(doc, actor, active_share):
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Insufficient permissions."
                    )
                )
                failed += 1
                continue

            await self._documents.soft_delete(doc_id)
            succeeded += 1
            results.append(BulkOperationResultItem(document_id=doc_id, success=True))

        await self._audit.create(
            action="document.bulk_delete",
            user_id=actor.id,
            table_name="documents",
            new_value={"total": len(document_ids), "succeeded": succeeded, "failed": failed},
            ip_address=ip_address,
        )
        await self._session.commit()

        return BulkOperationResponse(
            message=f"Bulk delete completed: {succeeded} succeeded, {failed} failed.",
            total=len(document_ids),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def bulk_tag(
        self,
        document_ids: list[uuid.UUID],
        tags: list[str],
        *,
        replace: bool = False,
        actor: User,
        ip_address: str | None = None,
    ) -> BulkOperationResponse:
        """Add or replace tags across multiple documents."""
        if len(document_ids) > settings.DOCUMENT_BULK_MAX_ITEMS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Batch size exceeds maximum limit of {settings.DOCUMENT_BULK_MAX_ITEMS} items.",
            )

        docs = await self._documents.get_by_ids(document_ids)
        doc_map = {d.id: d for d in docs}

        results: list[BulkOperationResultItem] = []
        succeeded = 0
        failed = 0

        for doc_id in document_ids:
            doc = doc_map.get(doc_id)
            if not doc:
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Document not found."
                    )
                )
                failed += 1
                continue

            active_share = await self._shares.get_active_share(doc.id, actor.id)
            if not DocumentAccessService.can_edit(doc, actor, active_share):
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Insufficient permissions."
                    )
                )
                failed += 1
                continue

            if replace:
                new_tags = list(dict.fromkeys(tags))
            else:
                existing = doc.tags or []
                new_tags = list(dict.fromkeys(existing + tags))

            await self._documents.update_metadata(doc.id, tags=new_tags)
            succeeded += 1
            results.append(BulkOperationResultItem(document_id=doc_id, success=True))

        await self._audit.create(
            action="document.bulk_tag",
            user_id=actor.id,
            table_name="documents",
            new_value={
                "total": len(document_ids),
                "succeeded": succeeded,
                "failed": failed,
                "tags": tags,
            },
            ip_address=ip_address,
        )
        await self._session.commit()

        return BulkOperationResponse(
            message=f"Bulk tagging completed: {succeeded} succeeded, {failed} failed.",
            total=len(document_ids),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    async def bulk_share(
        self,
        document_ids: list[uuid.UUID],
        target_user_id: uuid.UUID,
        permission: DocumentSharePermission,
        expires_at: datetime | None,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> BulkOperationResponse:
        """Share multiple documents with a user."""
        if len(document_ids) > settings.DOCUMENT_BULK_MAX_ITEMS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Batch size exceeds maximum limit of {settings.DOCUMENT_BULK_MAX_ITEMS} items.",
            )

        target_user = await self._users.get_by_id(target_user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found."
            )

        docs = await self._documents.get_by_ids(document_ids)
        doc_map = {d.id: d for d in docs}

        results: list[BulkOperationResultItem] = []
        succeeded = 0
        failed = 0

        for doc_id in document_ids:
            doc = doc_map.get(doc_id)
            if not doc:
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Document not found."
                    )
                )
                failed += 1
                continue

            active_share = await self._shares.get_active_share(doc.id, actor.id)
            if not DocumentAccessService.can_manage(doc, actor, active_share):
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Insufficient permissions."
                    )
                )
                failed += 1
                continue

            if doc.owner_id == target_user_id:
                results.append(
                    BulkOperationResultItem(
                        document_id=doc_id, success=False, reason="Target user is document owner."
                    )
                )
                failed += 1
                continue

            await self._shares.create_or_update(
                document_id=doc.id,
                user_id=target_user_id,
                granted_by=actor.id,
                permission=permission,
                expires_at=expires_at,
            )
            succeeded += 1
            results.append(BulkOperationResultItem(document_id=doc_id, success=True))

        await self._audit.create(
            action="document.bulk_share",
            user_id=actor.id,
            table_name="documents",
            new_value={
                "total": len(document_ids),
                "succeeded": succeeded,
                "grantee_id": str(target_user_id),
            },
            ip_address=ip_address,
        )

        if succeeded > 0:
            try:
                await self._notifs.create(
                    user_id=target_user_id,
                    title="Multiple Documents Shared",
                    message=f"{actor.first_name} {actor.last_name} shared {succeeded} document(s) with you ({permission.value} access).",
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.MEDIUM,
                )
            except Exception as notif_exc:
                logger.warning("Failed to send bulk share notification: %s", notif_exc)

        await self._session.commit()

        return BulkOperationResponse(
            message=f"Bulk share completed: {succeeded} succeeded, {failed} failed.",
            total=len(document_ids),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    # =========================================================================
    # 7. Document Activity Timeline
    # =========================================================================

    async def get_document_activity(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        limit: int = 50,
        offset: int = 0,
    ) -> DocumentActivityResponse:
        """Fetch sanitized activity history for a document."""
        doc = await self._documents.get_by_id(document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_view(doc, actor, active_share):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        result = await self._session.execute(
            select(AuditLog)
            .where(
                AuditLog.record_id == document_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        logs = list(result.scalars().all())

        total_res = await self._session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.record_id == document_id)
        )
        total_count = total_res.scalar_one()

        items: list[DocumentActivityItem] = []
        for log in logs:
            u = log.user
            summary = self._format_activity_summary(log)
            items.append(
                DocumentActivityItem(
                    id=log.id,
                    action=log.action,
                    actor_id=log.user_id,
                    actor_name=f"{u.first_name} {u.last_name}" if u else "System",
                    actor_email=u.email if u else None,
                    timestamp=log.created_at,
                    summary=summary,
                    details=log.new_value or {},
                )
            )

        return DocumentActivityResponse(
            document_id=document_id,
            data=items,
            total_events=total_count,
        )

    @staticmethod
    def _format_activity_summary(log: AuditLog) -> str:
        """Generate user-friendly activity descriptions."""
        action = log.action
        actor_name = f"{log.user.first_name} {log.user.last_name}" if log.user else "System"

        if action == "document.upload":
            return f"{actor_name} uploaded the document (Version 1)."
        if action == "document.version_created":
            v = log.new_value.get("version_number", "new") if log.new_value else "new"
            return f"{actor_name} created Version {v}."
        if action == "document.version_restored":
            v = log.new_value.get("new_version_number", "restored") if log.new_value else "restored"
            from_v = log.new_value.get("restored_from_version", "") if log.new_value else ""
            return f"{actor_name} restored Version {from_v} as Version {v}."
        if action == "document.shared":
            perm = log.new_value.get("permission", "view") if log.new_value else "view"
            return f"{actor_name} shared the document with {perm} permission."
        if action == "document.share_revoked":
            return f"{actor_name} revoked a document share grant."
        if action == "document.share_updated":
            return f"{actor_name} updated document share permissions."
        if action == "document.activated":
            return f"{actor_name} activated the document."
        if action == "document.archived":
            return f"{actor_name} archived the document."
        if action == "document.restored":
            return f"{actor_name} restored the document to active state."
        if action == "document.expired":
            return "Document reached its expiration date and transitioned to expired."
        if action == "document.delete":
            return f"{actor_name} deleted the document."
        if action == "document.update":
            return f"{actor_name} updated document metadata."
        if action == "document.download":
            return f"{actor_name} downloaded the document."
        if action == "document.view":
            return f"{actor_name} previewed the document."
        if action == "document.ai_summary":
            return f"{actor_name} requested an AI summary."
        if action == "document.ai_chat":
            return f"{actor_name} queried the document via AI chat."
        if action == "document.ocr_complete":
            return "Automated OCR and text extraction completed."
        return f"{action} performed by {actor_name}."

    # =========================================================================
    # 8. Streaming Downloads & In-Browser Preview
    # =========================================================================

    async def get_document_file_path(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> tuple[Path, str, str, int]:
        """Verify download authorization and return current version physical file path."""
        doc = await self._documents.get_by_id(document_id)
        if doc is None or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_download(doc, actor, active_share):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to download this document.",
            )

        resolved_path = self._storage.resolve_path(doc.storage_path)
        content_type = doc.file_type or "application/octet-stream"
        file_size = doc.file_size or resolved_path.stat().st_size

        await self._audit.create(
            action="document.download",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            new_value={"file_name": doc.file_name, "file_size": file_size},
            ip_address=ip_address,
        )
        await self._session.commit()

        return resolved_path, doc.file_name, content_type, file_size

    async def get_document_preview_path(
        self,
        document_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> tuple[Path, str, str, int]:
        """Verify view authorization and return current version physical file path for in-browser preview."""
        doc = await self._documents.get_by_id(document_id)
        if doc is None or doc.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

        active_share = await self._shares.get_active_share(doc.id, actor.id)
        if not DocumentAccessService.can_view(doc, actor, active_share):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to preview this document.",
            )

        resolved_path = self._storage.resolve_path(doc.storage_path)
        content_type = doc.file_type or "application/octet-stream"
        file_size = doc.file_size or resolved_path.stat().st_size

        await self._audit.create(
            action="document.view",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            new_value={"file_name": doc.file_name},
            ip_address=ip_address,
        )
        await self._session.commit()

        return resolved_path, doc.file_name, content_type, file_size

    # =========================================================================
    # 9. Legacy Metadata Creation (Backwards Compatibility)
    # =========================================================================

    async def create_document(
        self,
        data: DocumentCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DocumentResponse:
        """Create document metadata."""
        doc = await self._documents.create(
            file_name=data.file_name,
            title=data.title or data.file_name,
            description=data.description,
            category=data.category,
            document_type=data.document_type,
            tags=data.tags or [],
            department_id=data.department_id or actor.department_id,
            confidentiality=data.confidentiality,
            retention_period_days=data.retention_period_days,
            expires_at=data.expires_at,
            storage_path=data.storage_path,
            owner_id=actor.id,
            file_type=data.file_type,
            file_size=data.file_size,
            checksum=data.checksum,
        )

        await self._versions.create(
            document_id=doc.id,
            version_number=1,
            file_name=data.file_name,
            storage_path=data.storage_path,
            created_by=actor.id,
            file_type=data.file_type,
            file_size=data.file_size,
            checksum=data.checksum,
            is_current=True,
            change_summary="Initial upload (Version 1)",
        )

        await self._audit.create(
            action="document.create",
            user_id=actor.id,
            table_name="documents",
            record_id=doc.id,
            new_value={"file_name": doc.file_name, "owner_id": str(doc.owner_id)},
            ip_address=ip_address,
        )
        await self._session.commit()
        return _format_document_response(doc, actor)
