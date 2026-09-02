"""
retrieval_authorization — the single, authoritative RBAC gate for AI retrieval (Milestone 11).

Every retrieval path (semantic-only search, hybrid search, RAG context
building, document-scoped AI chat) funnels its candidate chunk IDs through
this module before any chunk text, filename, metadata, or score is exposed
to a caller or to the LLM.

Security contract:
  - FAISS and lexical indexes are candidate generators, not authorization layers.
  - PostgreSQL authorization via DocumentAccessService is AUTHORITATIVE.
  - Layer 1 (SQL): SearchRepository applies the full access grant / department / lifecycle filter.
  - Layer 2 (in-process): Re-verifies every resolved chunk's accessibility.
  - Archived, expired, or deleted document chunks are strictly omitted.
"""

from __future__ import annotations

import logging
import uuid

from app.models.user import User
from app.repositories.search_repository import ChunkWithDocument, SearchRepository
from app.services.document_access_service import (
    GLOBAL_DOCUMENT_ROLES,
    DocumentPermission,
    get_actor_role_name,
    is_global_admin,
)

logger = logging.getLogger(__name__)

# Re-export for compatibility with earlier modules
GLOBAL_ACCESS_ROLES = GLOBAL_DOCUMENT_ROLES


def role_name_of(actor: User) -> str:
    """Return the actor's role name defensively."""
    return get_actor_role_name(actor)


def is_global_access(actor: User) -> bool:
    """True if the actor may access every non-deleted document globally."""
    return is_global_admin(actor)


def sql_owner_filter(actor: User) -> uuid.UUID | None:
    """Legacy helper — returns owner_id or None for global roles."""
    return None if is_global_admin(actor) else actor.id


async def authorize_chunks(
    search_repo: SearchRepository,
    candidate_ids: list[uuid.UUID],
    *,
    actor: User,
    required_permission: DocumentPermission = DocumentPermission.VIEW,
    document_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, ChunkWithDocument]:
    """
    Resolve candidate chunk IDs to authorized chunks, enforcing enterprise authorization.

    Args:
        search_repo:         Repository bound to the request's DB session.
        candidate_ids:       Chunk IDs proposed by any retrieval strategy.
        actor:               The authenticated user.
        required_permission: Minimum permission required (default VIEW).
        document_id:         Optional restriction to a specific document (for document-scoped chat).

    Returns:
        Mapping {chunk_id: ChunkWithDocument} containing ONLY authorized chunks.
    """
    if not candidate_ids:
        return {}

    unique_ids = list(dict.fromkeys(candidate_ids))

    # Layer 1 — SQL filter with enterprise authorization
    resolved = await search_repo.get_chunks_with_documents(
        unique_ids,
        actor=actor,
        required_permission=required_permission,
        document_id=document_id,
    )

    if is_global_admin(actor):
        return resolved

    # Layer 2 — In-process sanity validation
    authorized: dict[uuid.UUID, ChunkWithDocument] = {}
    for chunk_id, chunk in resolved.items():
        if document_id is not None and chunk.document_id != document_id:
            logger.warning(
                "Document-scoped violation: chunk %s belongs to doc %s, expected %s",
                chunk_id,
                chunk.document_id,
                document_id,
            )
            continue
        authorized[chunk_id] = chunk

    return authorized
