"""
DocumentAccessService — Centralized, authoritative document authorization policy.

Provides the single source of truth for all document authorization checks:
  - Document lists & details
  - Version creation & restoration
  - Document sharing & permission management
  - Streaming downloads & previews
  - Full-text, semantic, and hybrid search
  - AI document summaries & document-scoped chat
  - Retrieval-Augmented Generation (RAG) context assembly
  - Bulk document operations
  - Document lifecycle transitions (activate, archive, expire, restore, delete)

Hierarchy & Evaluation:
  1. Role-based Global Access:
     - Admin & HR roles have global MANAGE permissions across all non-deleted documents.
     - Admin can also view and restore deleted documents.
  2. Ownership:
     - The document's creator/owner has full MANAGE permissions on their documents.
  3. Direct Access Grants (Shares):
     - Explicit active shares (not revoked, not expired) grant the designated permission
       (view, download, edit, manage).
  4. Department-Level Access:
     - If document.department_id matches actor.department_id (and both are not None):
       - Department Managers have MANAGE/EDIT permission (unless restricted).
       - Department Members have VIEW and DOWNLOAD permissions (unless restricted).
  5. Organization-wide Public Access:
     - Documents marked 'public' allow VIEW and DOWNLOAD to all active users.
     - Documents marked 'internal' or 'confidential' are scoped to owner, direct shares, and department members.
     - Documents marked 'restricted' require explicit direct share, ownership, or Admin/HR role.
  6. Lifecycle Filtering:
     - Archived, Expired, and Deleted documents are strictly excluded from normal
       AI retrieval and general search results.
"""

from __future__ import annotations

import enum
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentConfidentiality, DocumentLifecycleStatus
from app.models.document_share import DocumentShare, DocumentSharePermission
from app.models.user import User

logger = logging.getLogger(__name__)

# Roles with global administrative document access
GLOBAL_DOCUMENT_ROLES = frozenset({"admin", "hr"})


class DocumentPermission(str, enum.Enum):
    """Granular permission levels."""

    VIEW = "view"
    DOWNLOAD = "download"
    EDIT = "edit"
    MANAGE = "manage"


# Permission hierarchy mapping: higher permissions inherit lower ones
_PERMISSION_LEVELS: dict[str, int] = {
    DocumentPermission.VIEW.value: 10,
    DocumentPermission.DOWNLOAD.value: 20,
    DocumentPermission.EDIT.value: 30,
    DocumentPermission.MANAGE.value: 40,
}


def _has_permission(
    granted: str | DocumentSharePermission | DocumentPermission, required: DocumentPermission
) -> bool:
    """Check if granted permission satisfies the required permission level."""
    g_val = granted.value if hasattr(granted, "value") else str(granted)
    r_val = required.value if hasattr(required, "value") else str(required)
    return _PERMISSION_LEVELS.get(g_val, 0) >= _PERMISSION_LEVELS.get(r_val, 0)


def get_actor_role_name(actor: User) -> str:
    """Safely extract the actor's role name in lowercase."""
    if actor.role and hasattr(actor.role, "name") and actor.role.name:
        return actor.role.name.lower()
    return str(getattr(actor, "role", "employee")).lower()


def is_global_admin(actor: User) -> bool:
    """True if the actor possesses global document access privileges (admin / hr)."""
    return get_actor_role_name(actor) in GLOBAL_DOCUMENT_ROLES


class DocumentAccessService:
    """Authoritative document access evaluator and query filter generator."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self._session = db

    # =========================================================================
    # Synchronous in-memory permission evaluation
    # =========================================================================

    @staticmethod
    def evaluate_permission(
        document: Document,
        actor: User,
        active_share: DocumentShare | None = None,
    ) -> DocumentPermission | None:
        """
        Evaluate the maximum permission level the actor holds on the document.

        Returns:
            DocumentPermission or None if the actor has no access.
        """
        role = get_actor_role_name(actor)

        # 1. Global Admin / HR
        if role in GLOBAL_DOCUMENT_ROLES:
            return DocumentPermission.MANAGE

        # 2. Document Owner
        if document.owner_id == actor.id:
            return DocumentPermission.MANAGE

        # 3. Direct Active Share
        if active_share is not None and active_share.is_active:
            perm_val = getattr(active_share.permission, "value", str(active_share.permission))
            if perm_val == DocumentSharePermission.MANAGE.value:
                return DocumentPermission.MANAGE
            if perm_val == DocumentSharePermission.EDIT.value:
                return DocumentPermission.EDIT
            if perm_val == DocumentSharePermission.DOWNLOAD.value:
                return DocumentPermission.DOWNLOAD
            return DocumentPermission.VIEW

        # Check if document has shares loaded
        if hasattr(document, "shares") and document.shares:
            for share in document.shares:
                if str(share.user_id) == str(actor.id) and share.is_active:
                    perm_val = getattr(share.permission, "value", str(share.permission))
                    if perm_val == DocumentSharePermission.MANAGE.value:
                        return DocumentPermission.MANAGE
                    if perm_val == DocumentSharePermission.EDIT.value:
                        return DocumentPermission.EDIT
                    if perm_val == DocumentSharePermission.DOWNLOAD.value:
                        return DocumentPermission.DOWNLOAD
                    return DocumentPermission.VIEW

        # 4. Restricted confidentiality blocks department & org-wide fallback
        is_restricted = document.confidentiality == DocumentConfidentiality.RESTRICTED
        if is_restricted:
            return None

        # 5. Department Match (requires non-null department on both document and user)
        if (
            document.department_id is not None
            and actor.department_id is not None
            and document.department_id == actor.department_id
        ):
            if role == "manager":
                return DocumentPermission.MANAGE
            return DocumentPermission.DOWNLOAD

        # 6. Public Organization-wide Access
        if document.confidentiality == DocumentConfidentiality.PUBLIC:
            return DocumentPermission.DOWNLOAD

        return None

    @classmethod
    def can_view(
        cls,
        document: Document,
        actor: User,
        active_share: DocumentShare | None = None,
    ) -> bool:
        """Check if actor can view document metadata and content."""
        perm = cls.evaluate_permission(document, actor, active_share)
        return perm is not None and _has_permission(perm, DocumentPermission.VIEW)

    @classmethod
    def can_download(
        cls,
        document: Document,
        actor: User,
        active_share: DocumentShare | None = None,
    ) -> bool:
        """Check if actor can download the document or its versions."""
        perm = cls.evaluate_permission(document, actor, active_share)
        return perm is not None and _has_permission(perm, DocumentPermission.DOWNLOAD)

    @classmethod
    def can_edit(
        cls,
        document: Document,
        actor: User,
        active_share: DocumentShare | None = None,
    ) -> bool:
        """Check if actor can update metadata, upload versions, or tag document."""
        perm = cls.evaluate_permission(document, actor, active_share)
        return perm is not None and _has_permission(perm, DocumentPermission.EDIT)

    @classmethod
    def can_manage(
        cls,
        document: Document,
        actor: User,
        active_share: DocumentShare | None = None,
    ) -> bool:
        """Check if actor can manage shares, lifecycle states, or delete document."""
        perm = cls.evaluate_permission(document, actor, active_share)
        return perm is not None and _has_permission(perm, DocumentPermission.MANAGE)

    # =========================================================================
    # SQL Filter Generators for Single Batched Retrieval & Search
    # =========================================================================

    @staticmethod
    def build_authorization_filter(
        actor: User,
        required_permission: DocumentPermission = DocumentPermission.VIEW,
        *,
        include_archived: bool = False,
        include_deleted: bool = False,
    ) -> Any:
        """
        Construct a SQLAlchemy binary expression enforcing the full authorization
        policy in a single SQL query (preventing N+1 roundtrips).
        """
        role = get_actor_role_name(actor)
        is_global = role in GLOBAL_DOCUMENT_ROLES

        now = datetime.now(UTC)

        conditions: list[Any] = []

        if not include_deleted:
            conditions.append(Document.deleted_at.is_(None))
            conditions.append(Document.lifecycle_status != DocumentLifecycleStatus.DELETED)

        if not include_archived:
            conditions.append(Document.lifecycle_status != DocumentLifecycleStatus.ARCHIVED)
            conditions.append(Document.lifecycle_status != DocumentLifecycleStatus.EXPIRED)

        if is_global:
            return conditions

        # Non-global users: Build union of valid authorization branches
        auth_branches: list[Any] = [
            # Branch 1: Owned documents
            Document.owner_id == actor.id,
        ]

        # Branch 2: Active direct shares with sufficient permission
        valid_share_subquery = select(DocumentShare.document_id).where(
            DocumentShare.user_id == actor.id,
            DocumentShare.revoked_at.is_(None),
            or_(
                DocumentShare.expires_at.is_(None),
                DocumentShare.expires_at > now,
            ),
        )

        if required_permission == DocumentPermission.MANAGE:
            valid_share_subquery = valid_share_subquery.where(
                DocumentShare.permission == DocumentSharePermission.MANAGE
            )
        elif required_permission == DocumentPermission.EDIT:
            valid_share_subquery = valid_share_subquery.where(
                DocumentShare.permission.in_(
                    [DocumentSharePermission.MANAGE, DocumentSharePermission.EDIT]
                )
            )
        elif required_permission == DocumentPermission.DOWNLOAD:
            valid_share_subquery = valid_share_subquery.where(
                DocumentShare.permission.in_(
                    [
                        DocumentSharePermission.MANAGE,
                        DocumentSharePermission.EDIT,
                        DocumentSharePermission.DOWNLOAD,
                    ]
                )
            )

        auth_branches.append(Document.id.in_(valid_share_subquery))

        # Branch 3: Department match (non-restricted documents, both non-null)
        if actor.department_id is not None:
            dept_condition = (
                (Document.department_id.is_not(None))
                & (Document.department_id == actor.department_id)
                & (Document.confidentiality != DocumentConfidentiality.RESTRICTED)
            )

            if required_permission == DocumentPermission.MANAGE:
                if role == "manager":
                    auth_branches.append(dept_condition)
            elif required_permission == DocumentPermission.EDIT:
                if role == "manager":
                    auth_branches.append(dept_condition)
            else:
                auth_branches.append(dept_condition)

        # Branch 4: Organization-wide public
        auth_branches.append(Document.confidentiality == DocumentConfidentiality.PUBLIC)

        conditions.append(or_(*auth_branches))
        return conditions
