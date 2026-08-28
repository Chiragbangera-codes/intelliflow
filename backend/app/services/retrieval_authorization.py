"""
retrieval_authorization — the single, authoritative RBAC gate for AI retrieval.

Every retrieval path (semantic-only search, hybrid search, RAG context
building) funnels its candidate chunk IDs through this module before any chunk
text, filename, metadata, or score is exposed to a caller or to the LLM.

Security contract (Milestone 7 Phase 1/23 — verbatim intent):
  - FAISS is NEVER an authorization layer. Neither is the lexical index. They
    are candidate *generators*. PostgreSQL ownership is authoritative.
  - Two independent layers, both enforced here:
      Layer 1 (SQL): SearchRepository.get_chunks_with_documents applies
        WHERE document.owner_id = actor.id   for employees/managers,
        or no owner restriction               for admin/HR,
        always excluding soft-deleted documents.
      Layer 2 (in-process): every resolved chunk is re-checked so a chunk whose
        owner is not the actor can never survive, even if Layer 1 were somehow
        bypassed. Admin/HR bypass the ownership comparison (global access).
  - Chunks that are stale (deleted from the DB) or unauthorized are simply
    absent from the result — their existence, filename, and content are never
    revealed.

This module holds no query logic and does not log query text.
"""

from __future__ import annotations

import logging
import uuid

from app.models.user import User
from app.repositories.search_repository import ChunkWithDocument, SearchRepository

logger = logging.getLogger(__name__)

# Roles that may access all non-deleted documents globally (bypass ownership).
# Canonical definition — imported by the semantic and hybrid services so the
# rule lives in exactly one place.
GLOBAL_ACCESS_ROLES = frozenset({"admin", "hr"})


def role_name_of(actor: User) -> str:
    """Return the actor's role name defensively (handles ORM or raw values)."""
    return actor.role.name if hasattr(actor.role, "name") else str(actor.role)


def is_global_access(actor: User) -> bool:
    """True if the actor may access every non-deleted document (admin/HR)."""
    return role_name_of(actor) in GLOBAL_ACCESS_ROLES


def sql_owner_filter(actor: User) -> uuid.UUID | None:
    """
    Return the owner_id to filter by in SQL (Layer 1), or None for global roles.

    None means "no owner restriction" and must only ever be produced for
    admin/HR. Employees and managers always get their own id.
    """
    return None if is_global_access(actor) else actor.id


async def authorize_chunks(
    search_repo: SearchRepository,
    candidate_ids: list[uuid.UUID],
    *,
    actor: User,
) -> dict[uuid.UUID, ChunkWithDocument]:
    """
    Resolve candidate chunk IDs to authorized chunks, enforcing both RBAC layers.

    Args:
        search_repo:   Repository bound to the request's DB session.
        candidate_ids: Chunk IDs proposed by any retrieval strategy (semantic,
                       lexical, document-aware). Order and origin are irrelevant
                       to authorization.
        actor:         The authenticated user.

    Returns:
        A mapping {chunk_id: ChunkWithDocument} containing ONLY chunks the actor
        is authorized to see. Unauthorized, stale, or non-existent IDs are
        omitted. Never raises on unauthorized input — it filters silently.
    """
    if not candidate_ids:
        return {}

    # De-duplicate while bounding the batch; order does not matter here because
    # ranking is applied by the caller after authorization.
    unique_ids = list(dict.fromkeys(candidate_ids))

    is_global = is_global_access(actor)
    owner_id = None if is_global else actor.id

    # Layer 1 — SQL owner filter + soft-delete exclusion (single batched query).
    resolved = await search_repo.get_chunks_with_documents(unique_ids, owner_id=owner_id)

    if is_global:
        return resolved

    # Layer 2 — in-process ownership re-check (defence in depth). A mismatch here
    # means Layer 1 failed to exclude a foreign document; drop it and warn.
    authorized: dict[uuid.UUID, ChunkWithDocument] = {}
    for chunk_id, chunk in resolved.items():
        if chunk.document_owner_id != actor.id:
            logger.warning(
                "RBAC layer-2 drop: chunk_id=%s owner=%s actor=%s (SQL filter should "
                "have excluded this).",
                chunk_id,
                chunk.document_owner_id,
                actor.id,
            )
            continue
        authorized[chunk_id] = chunk
    return authorized
